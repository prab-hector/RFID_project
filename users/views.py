import random
import re
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from .models import AttendanceLog, Teammates
from django.contrib.auth.decorators import login_required
from .forms import StorageUpdateForm
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth import update_session_auth_hash, login as auth_login
from django.contrib.auth import logout as django_logout
from django.contrib.auth.models import User
from datetime import datetime
from django.shortcuts import HttpResponse


# CRITICAL FIX: Import your buffer from your hardware/gateway app folder
# Replace 'your_hardware_app_name' with your actual app folder name (e.g., storage, rfid_datacoming, etc.)

def home_dashboard(request):
    today = timezone.localdate()

    # Delete old attendance logs older than the first day of the current month
    first_of_month = today.replace(day=1)
    AttendanceLog.objects.filter(timestamp__date__lt=first_of_month).delete()

    selected_date_str = request.GET.get('date')
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = today
    else:
        selected_date = today

    attendance_logs = AttendanceLog.objects.select_related('teammate').filter(timestamp__date=selected_date).order_by('timestamp')

    # 2. Fetch incomplete profiles (Auto-created by process_rfid)
    incomplete_profiles = Teammates.objects.filter(is_fully_registered=False).order_by('-date_posted')

    # Admin initials logic
    if request.user.is_authenticated:
        admin_name = request.user.get_full_name() or request.user.username
    else:
        admin_name = "Guest Admin"
    admin_initials = "".join([n[0] for n in admin_name.split() if n])[:2].upper()

    total_students = Teammates.objects.filter(is_fully_registered=True).count()
    present_count = attendance_logs.filter(teammate__isnull=False).values('teammate').distinct().count()
    absent_count = max(0, total_students - present_count) if total_students > 0 else 0
    attendance_pct = f"{round((present_count / total_students) * 100)}%" if total_students > 0 else "0%"

    context = {
        'attendance_logs': attendance_logs,
        'selected_date': selected_date,
        'today': today,
        'incomplete_profiles': incomplete_profiles,
        'admin_name': admin_name,
        'admin_initials': admin_initials,
        'user': request.user,
        'total_students': total_students,
        'present_count': present_count,
        'absent_count': absent_count,
        'attendance_pct': attendance_pct,
    }
    
    # Fixed typo: 'contex' -> 'context'
    return render(request, 'users/homepg.html', context)

def login(request):
    """
    Authentication View: Renders user portal entry page template layout context.
    """
    return render(request, 'users/login.html')

def set_password(request, pk): # 1. Accept pk as an argument
    # 2. Use pk to fetch only the specific user
    target_user = get_object_or_404(User, pk=pk) 
    
    if request.method == 'POST':
        form = SetPasswordForm(target_user, request.POST) 
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            auth_login(request, user)
            # 3. Redirect using the specific user's pk
            return redirect('edit_profile', pk=user.pk)
    else:
        form = SetPasswordForm(target_user)
        
    return render(request, 'users/set_password.html', {'form': form})



@login_required
def logout(request):
    django_logout(request)  # This terminates the active session
    return redirect('homepg')  # This bounces them directly back to the dashboard

@login_required
def profile(request):
     user_storage_records = Teammates.objects.filter(author = request.user)

     context = {
          'records': user_storage_records
     }
     return render(request, 'users/profile.html',context)


def _normalize_username(value):
    username = str(value).strip().lower()
    username = re.sub(r'[^a-z0-9._+-]+', '_', username)
    username = re.sub(r'_+', '_', username).strip('_')
    return username or f"user_{random.randint(1000,9999)}"


def _generate_unique_username_from_name(name, current_user=None):
    base = _normalize_username(name)
    username = base
    counter = 1
    queryset = User.objects.exclude(pk=current_user.pk) if current_user else User.objects.all()
    while queryset.filter(username=username).exists():
        username = f"{base}_{counter}"
        counter += 1
    return username

@login_required
def edit_profile(request, pk):
    if request.user.pk != pk:
        return redirect('homepg')

    storage_instance = Teammates.objects.filter(author=request.user).first()
    if storage_instance is None:
        storage_instance = Teammates(
            author=request.user,
            rfid_number=f"T{request.user.pk:07d}",
            phone_number="0000000000",
            is_fully_registered=False,
        )
    was_pending_registration = not storage_instance.is_fully_registered

    if request.method == 'POST':
        if not request.user.has_usable_password():
            messages.warning(request, "You must set a password before updating your profile.")
            return redirect('homepg')

        s_form = StorageUpdateForm(request.POST, instance=storage_instance)

        if s_form.is_valid():
            storage_item = s_form.save(commit=False)
            if not storage_item.author_id:
                storage_item.author = request.user
            if not storage_item.rfid_number:
                storage_item.rfid_number = f"T{request.user.pk:07d}"
            storage_item.is_fully_registered = storage_item.phone_number != "0000000000"
            storage_item.save()

            new_username = _generate_unique_username_from_name(storage_item.name, current_user=request.user)
            request.user.username = new_username
            request.user.email = storage_item.email
            request.user.save(update_fields=['username', 'email'])

            if storage_item.is_fully_registered:
                today = timezone.localdate()
                attendance_log = AttendanceLog.objects.filter(
                    teammate=storage_item,
                    timestamp__date=today,
                ).order_by('timestamp').first()

                if attendance_log:
                    if attendance_log.status != "Present":
                        attendance_log.status = "Present"
                        attendance_log.save(update_fields=['status'])
                else:
                    attendance_log = AttendanceLog.objects.create(
                        teammate=storage_item,
                        status="Present",
                    )

                try:
                    from data_flow.service import push_attendance_to_sheets
                    push_attendance_to_sheets(attendance_log)
                except Exception as e:
                    print(f"Sync Error: {e}")

            if storage_item.is_fully_registered and was_pending_registration:
                messages.success(request, "Profile updated successfully! Attendance marked present.")
            elif storage_item.is_fully_registered:
                messages.success(request, "Profile updated successfully!")
            else:
                messages.warning(request, "Profile updated, but registration is still pending until a valid phone number is provided.")
            return redirect('profile')
    else:
        s_form = StorageUpdateForm(instance=storage_instance)

    context = {
        's_form': s_form,
        'my_storage': storage_instance,
        'user_has_password': request.user.has_usable_password()
    }
    return render(request, 'users/edit_profile.html', context)
