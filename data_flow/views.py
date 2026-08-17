from django.shortcuts import render
import pandas as pd
import random
from django.http import HttpResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.csrf import csrf_exempt
from .service import push_attendance_to_sheets
from django.http import JsonResponse
import json
from datetime import datetime
from django.utils import timezone
from users.models import SystemState
from users.models import Teammates, AttendanceLog
from django.contrib.auth.models import User

# Create your views here.

# Use this for downloading the Excel report
def export_Attendance_Log(request):
    selected_date_str = request.GET.get('date')
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = timezone.localdate()
    else:
        selected_date = timezone.localdate()

    # Fetch data from SQLite
    logs = AttendanceLog.objects.filter(timestamp__date=selected_date)
    # Convert QuerySet to DataFrame
    data = [{
        'Name': log.teammate.name if log.teammate else 'Unknown',
        'Time': str(log.timestamp.time()),
        'Date': str(log.timestamp.date()),
        'Domain': log.teammate.domain if log.teammate else 'N/A',
        'Year': log.teammate.year if log.teammate else 'N/A',
        'Phone number': log.teammate.phone_number if log.teammate else 'N/A',
        'Email': log.teammate.email if log.teammate else 'N/A'
    } for log in logs]
    df = pd.DataFrame(data)
    # Generate Excel response
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="Attendance_{selected_date}.xlsx"'
    
    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
        
    return response


# Define your Master IDs here

MASTER_ENROLL_ID = "E25B2F45"

def _generate_random_username():
    while True:
        username = f"user_{random.randint(1000, 9999)}"
        if not User.objects.filter(username=username).exists():
            return username


def get_system_state():
    state, _ = SystemState.objects.get_or_create(pk=1)
    return state


def _activate_admin_mode():
    state = get_system_state()
    state.admin_mode_active = True
    state.admin_mode_expires = timezone.now() + timezone.timedelta(seconds=10)
    state.save()
    return state


def _consume_admin_mode():
    state = get_system_state()
    if not state.admin_mode_active:
        return False
    if state.admin_mode_expires and state.admin_mode_expires < timezone.now():
        state.admin_mode_active = False
        state.admin_mode_expires = None
        state.save()
        return False
    state.admin_mode_active = False
    state.admin_mode_expires = None
    state.save()
    return True


def _parse_rfid_request(request):
    try:
        body = request.body.decode('utf-8')
        data = json.loads(body) if body else {}
    except Exception:
        data = request.POST.dict()

    return {
        'rfid_id': data.get('rfid_id', '').strip().upper(),
        'mode': data.get('mode', '').strip().lower(),
    }


@csrf_exempt
def process_rfid(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)

    payload = _parse_rfid_request(request)
    rfid_uid = payload['rfid_id']
    mode = payload['mode']

    if not rfid_uid:
        return JsonResponse({'status': 'error', 'message': 'Missing rfid_id'}, status=400)

    # Master-card scan enters admin mode
    if rfid_uid == MASTER_ENROLL_ID:
        _activate_admin_mode()
        return JsonResponse({
            'status': 'admin_mode',
            'message': 'Master card recognized. Scan the target card to register or delete.',
        }, status=200)

    teammate = Teammates.objects.filter(rfid_number=rfid_uid).first()

    # Admin mode: create new card or delete existing card
    if mode == 'admin' or _consume_admin_mode():
        if teammate:
            teammate.author.delete()
            return JsonResponse({
                'status': 'deleted',
                'message': 'User deleted completely from the system.',
            }, status=200)

        username = _generate_random_username()
        email = f"nli{random.randint(1000,9999)}@gmail.com"
        new_user = User.objects.create_user(username=username, email=email)
        new_user.set_unusable_password()
        new_user.save()

        new_teammate = Teammates.objects.create(
            name=username,
            email=email,
            branch="Unassigned",
            phone_number="0000000000",
            year="Year",
            rfid_number=rfid_uid,
            is_fully_registered=False,
            author=new_user
        )

        return JsonResponse({
            'status': 'created',
            'message': 'New user placeholder created. Complete registration before normal attendance.',
            'user_id': new_user.pk,
            'teammate_id': new_teammate.pk,
        }, status=201)

    # Normal attendance flow
    if teammate:
        if not teammate.is_fully_registered or teammate.phone_number == "0000000000":
            return JsonResponse({
                'status': 'pending_registration',
                'message': 'Registration pending: complete your profile before marking attendance.',
            }, status=200)

        today = timezone.localdate()
        if AttendanceLog.objects.filter(teammate=teammate, timestamp__date=today).exists():
            return JsonResponse({
                'status': 'success',
                'message': 'Attendance already marked for today.',
                'already_marked': True,
            }, status=200)

        new_log = AttendanceLog.objects.create(teammate=teammate, status="Present")
        try:
            push_attendance_to_sheets(new_log)
        except Exception as e:
            print(f"Sync Error: {e}")

        return JsonResponse({'status': 'success', 'message': 'Attendance marked.'}, status=200)

    return JsonResponse({
        'status': 'error',
        'message': 'User not found. Scan master card to create this card or use a registered card for attendance.',
    }, status=404)
        
    

        

