from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime
import re
import random
import string
import uuid

app = Flask(__name__)
import os

app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev_secret_key_123')

# Admin credentials
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin@ec'

# Temporary data storage (will be replaced with SQLite later)
events_db = []
registrations_db = []
results_db = []
notifications_db = []

def validate_student_id(student_id):
    pattern = r'^YVA\d{3}$'
    return bool(re.match(pattern, student_id))

def generate_chest_number(category):
    random_digits = ''.join(random.choices(string.digits, k=4))
    return f"{category.upper()}{random_digits}"

def create_notification(message, type='admin'):
    notification = {
        'id': str(uuid.uuid4()),
        'message': message,
        'type': type,
        'timestamp': datetime.now().strftime("%Y-%m-%d %I:%M %p")
    }
    notifications_db.insert(0, notification)  # Add to beginning of list

def get_event_registrations(event_name):
    return [reg for reg in registrations_db if reg['event_name'] == event_name]

def get_event_by_name(event_name):
    return next((event for event in events_db if event['name'] == event_name), None)

def is_event_past(event_date):
    event_datetime = datetime.strptime(event_date, "%Y-%m-%d")
    current_datetime = datetime.now()
    return event_datetime.date() < current_datetime.date()

def get_active_events():
    current_datetime = datetime.now()
    return [event for event in events_db if not is_event_past(event['date'])]

def get_student_events(student_id):
    """Get list of event names that a student has registered for"""
    return [reg['event_name'] for reg in registrations_db if reg['student_id'] == student_id]

def get_events():
    return events_db

def is_student_registered(student_id, event_name):
    return any(reg['student_id'] == student_id and reg['event_name'] == event_name for reg in registrations_db)

def get_student_results(student_id):
    """Get results for a specific student"""
    return [result for result in results_db if result['student_id'] == student_id]

def get_all_results():
    """Get all results grouped by event"""
    results_by_event = {}
    for result in results_db:
        event_name = result['event_name']
        if event_name not in results_by_event:
            results_by_event[event_name] = []
        results_by_event[event_name].append(result)
    
    # Sort results within each event by position
    for event_results in results_by_event.values():
        event_results.sort(key=lambda x: x['position'])
    
    return results_by_event

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/student_login', methods=['POST'])
def student_login():
    student_id = request.form.get('student_id')
    if validate_student_id(student_id):
        session['user_id'] = student_id
        session['user_type'] = 'student'
        return redirect(url_for('dashboard'))
    flash('Invalid Student ID. ID should start with YVA followed by 3 numbers.')
    return redirect(url_for('index'))

@app.route('/admin_login', methods=['POST'])
def admin_login():
    username = request.form.get('username')
    password = request.form.get('password')
    
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session['user_type'] = 'admin'
        return redirect(url_for('admin_dashboard'))
    
    flash('Invalid admin credentials.')
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_type' not in session:
        return redirect(url_for('index'))
    
    # Get registered events for student
    registered_events = []
    if session.get('user_type') == 'student':
        student_id = session.get('user_id')
        registered_events = [reg for reg in registrations_db if reg['student_id'] == student_id]
    
    # Get notifications
    notifications = [n for n in notifications_db if n.get('user_id') == session.get('user_id') or n.get('user_id') is None]
    
    return render_template('dashboard.html', 
                         registered_events=registered_events,
                         notifications=notifications)

@app.route('/admin_dashboard')
def admin_dashboard():
    if session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    return render_template('admin_dashboard.html')

@app.route('/publish_event')
def publish_event():
    if session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    return render_template('publish_event.html', current_date=datetime.now().strftime('%Y-%m-%d'))

@app.route('/submit_event', methods=['POST'])
def submit_event():
    if session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    event = {
        'id': len(events_db) + 1,
        'name': request.form.get('event_name'),
        'category': request.form.get('category'),
        'venue': request.form.get('venue'),
        'date': request.form.get('date'),
        'time': datetime.strptime(request.form.get('time'), '%H:%M').strftime('%I:%M %p'),
        'description': request.form.get('description', '')
    }
    
    events_db.append(event)
    
    # Create notification for new event
    create_notification(
        f"New {event['category']} event '{event['name']}' has been published for {event['date']}!",
        type='event'
    )
    
    flash('Event published successfully!')
    return redirect(url_for('publish_event'))

@app.route('/view_registrations')
def view_registrations():
    """View all event registrations grouped by event"""
    if session.get('user_type') != 'admin':
        return redirect(url_for('index'))

    # Get all events and their details
    events_with_registrations = {}
    for event in events_db:
        events_with_registrations[event['name']] = {
            'event': event,
            'registrations': []
        }

    # Add registrations to their respective events
    for reg in registrations_db:
        if reg['event_name'] in events_with_registrations:
            events_with_registrations[reg['event_name']]['registrations'].append(reg)

    return render_template('view_registrations.html', events=events_with_registrations)

@app.route('/delete_event', methods=['POST'])
def delete_event():
    """Delete an event and its registrations"""
    if session.get('user_type') != 'admin':
        return redirect(url_for('index'))

    event_name = request.form.get('event_name')
    if not event_name:
        flash('Event name is required', 'error')
        return redirect(url_for('view_registrations'))

    # Count registrations for this event
    registration_count = sum(1 for reg in registrations_db if reg['event_name'] == event_name)
    if registration_count >= 3:
        flash('Cannot delete event with 3 or more registrations', 'error')
        return redirect(url_for('view_registrations'))

    # Remove event from events_db
    events_db[:] = [e for e in events_db if e['name'] != event_name]
    
    # Remove all registrations for this event
    registrations_db[:] = [r for r in registrations_db if r['event_name'] != event_name]

    # Create notification
    notification = {
        'type': 'admin',
        'message': f'Event {event_name} has been cancelled',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    notifications_db.append(notification)

    flash(f'Event {event_name} has been deleted successfully', 'success')
    return redirect(url_for('view_registrations'))

@app.route('/publish_notification')
def publish_notification():
    if session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    return render_template('publish_notification.html', notifications=notifications_db)

@app.route('/submit_notification', methods=['POST'])
def submit_notification():
    if session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    message = request.form.get('message')
    create_notification(message, type='admin')
    
    flash('Notification published successfully!')
    return redirect(url_for('publish_notification'))

@app.route('/delete_notification', methods=['POST'])
def delete_notification():
    if session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    notification_id = request.form.get('notification_id')
    global notifications_db
    notifications_db = [n for n in notifications_db if n['id'] != notification_id]
    
    flash('Notification deleted successfully!')
    return redirect(url_for('publish_notification'))

@app.route('/register_event')
def register_event():
    if 'user_type' not in session or session['user_type'] != 'student':
        return redirect(url_for('index'))
    
    registered_events = get_student_events(session['user_id'])
    return render_template('register_event.html', events=events_db, registered_events=registered_events)

@app.route('/submit_registration', methods=['POST'])
def submit_registration():
    if 'user_type' not in session or session['user_type'] != 'student':
        return redirect(url_for('index'))

    event_name = request.form.get('event_name')
    name = request.form.get('name')
    student_class = request.form.get('class')
    department = request.form.get('department')

    if not all([event_name, name, student_class, department]):
        flash('All fields are required', 'error')
        return redirect(url_for('register_event'))

    # Check if already registered
    if event_name in get_student_events(session['user_id']):
        flash('You are already registered for this event', 'error')
        return redirect(url_for('register_event'))

    # Get event details
    event = next((e for e in events_db if e['name'] == event_name), None)
    if not event:
        flash('Event not found', 'error')
        return redirect(url_for('register_event'))

    # Generate chest number
    chest_number = generate_chest_number(event['category'])
    
    # Register student
    registration = {
        'student_id': session['user_id'],
        'name': name,
        'class': student_class,
        'department': department,
        'event_name': event_name,
        'chest_number': chest_number,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    registrations_db.append(registration)

    # Create notification
    notification = {
        'type': 'event',
        'user_id': session['user_id'],
        'message': f'Successfully registered for {event_name}',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    notifications_db.append(notification)

    # Store registration in session for receipt page
    session['last_registration'] = registration
    session['last_event'] = event

    return redirect(url_for('registration_receipt'))

@app.route('/registration_receipt')
def registration_receipt():
    if 'user_type' not in session or session['user_type'] != 'student':
        return redirect(url_for('index'))
    
    registration = session.get('last_registration')
    event = session.get('last_event')
    
    if not registration or not event:
        flash('No recent registration found', 'error')
        return redirect(url_for('register_event'))
    
    # Clear the registration from session after showing
    session.pop('last_registration', None)
    session.pop('last_event', None)
    
    return render_template('registration_receipt.html', registration=registration, event=event)

@app.route('/upcoming_events')
def upcoming_events():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    active_events = get_active_events()
    registered_events = []
    
    if session.get('user_type') == 'student':
        student_id = session.get('user_id')
        registered_events = [reg['event_name'] for reg in registrations_db if reg['student_id'] == student_id]
    
    return render_template('upcoming_events.html', events=active_events, registered_events=registered_events)

@app.route('/my_events')
def my_events():
    if 'user_type' not in session or session['user_type'] != 'student':
        return redirect(url_for('index'))
    
    student_id = session.get('user_id')
    # Get all registrations for this student
    student_registrations = [reg for reg in registrations_db if reg['student_id'] == student_id]
    
    # Get full event details for each registration
    student_events = []
    for reg in student_registrations:
        event = next((e for e in events_db if e['name'] == reg['event_name']), None)
        if event:
            event_with_chest = event.copy()
            event_with_chest['chest_number'] = reg['chest_number']
            student_events.append(event_with_chest)
    
    return render_template('my_events.html', events=student_events)

@app.route('/publish_result')
def publish_result():
    if session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    # Get all events with their registrations
    events_with_registrations = []
    for event in events_db:
        event_copy = event.copy()
        event_copy['registrations'] = [
            {
                'chest_number': reg['chest_number'],
                'name': reg['name'],
                'class': reg['class'],
                'department': reg['department']
            }
            for reg in registrations_db 
            if reg['event_name'] == event['name']
        ]
        events_with_registrations.append(event_copy)
    
    return render_template('publish_result.html', events=events_with_registrations)

@app.route('/get_event_registrations/<event_name>')
def get_event_registrations_api(event_name):
    """API endpoint to get registrations for an event"""
    if session.get('user_type') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401

    registrations = [
        {
            'chest_number': reg['chest_number'],
            'name': reg['name'],
            'class': reg['class'],
            'department': reg['department']
        }
        for reg in registrations_db 
        if reg['event_name'] == event_name
    ]
    
    return jsonify(registrations)

@app.route('/get_registered_candidates/<event_name>')
def get_registered_candidates(event_name):
    """Get all registered candidates for an event"""
    if session.get('user_type') != 'admin':
        return redirect(url_for('index'))
        
    event = next((e for e in events_db if e['name'] == event_name), None)
    if not event:
        flash('Event not found', 'error')
        return redirect(url_for('admin_dashboard'))
        
    registrations = []
    for reg in registrations_db:
        if reg['event_name'] == event_name:
            registrations.append({
                'chest_number': reg['chest_number'],
                'name': reg['name'],
                'class': reg['class'],
                'department': reg['department'],
                'timestamp': reg['timestamp']
            })
            
    return render_template('view_registered_candidates.html', 
                         event=event, 
                         registrations=registrations)

@app.route('/submit_result', methods=['POST'])
def submit_result():
    """Submit event results"""
    if session.get('user_type') != 'admin':
        return redirect(url_for('index'))

    event_name = request.form.get('event_name')
    winners = request.form.getlist('winners[]')

    if not event_name or not winners:
        flash('Please select an event and add winners', 'error')
        return redirect(url_for('publish_result'))

    # Get event details
    event = next((e for e in events_db if e['name'] == event_name), None)
    if not event:
        flash('Event not found', 'error')
        return redirect(url_for('publish_result'))

    # Get registration details for winners
    winner_details = []
    for position, chest_number in enumerate(winners, 1):
        registration = next(
            (r for r in registrations_db if r['event_name'] == event_name and r['chest_number'] == chest_number),
            None
        )
        if registration:
            winner_details.append({
                'position': position,
                'chest_number': chest_number,
                'name': registration['name'],
                'class': registration['class'],
                'department': registration['department'],
                'student_id': registration['student_id']
            })

    # Create result entry
    result = {
        'event_name': event_name,
        'category': event['category'],
        'date': event['date'],
        'winners': winner_details,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    results_db.append(result)

    # Create notifications for winners
    for winner in winner_details:
        notification = {
            'type': 'result',
            'user_id': winner['student_id'],
            'message': f"Congratulations! You secured {winner['position']} position in {event_name}",
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        notifications_db.append(notification)

    # Create general notification
    notification = {
        'type': 'result',
        'message': f"Results for {event_name} have been published",
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    notifications_db.append(notification)

    flash(f'Results for {event_name} published successfully!', 'success')
    return redirect(url_for('result_board'))

@app.route('/result_board')
def result_board():
    """Display all event results"""
    # Group results by event category
    results_by_category = {}
    for result in results_db:
        category = result['category']
        if category not in results_by_category:
            results_by_category[category] = []
        results_by_category[category].append(result)
    
    # Sort results within each category by date
    for category in results_by_category:
        results_by_category[category].sort(key=lambda x: x['timestamp'], reverse=True)
    
    return render_template('result_board.html', results_by_category=results_by_category)

@app.route('/my_results')
def my_results():
    """Display results for the logged-in student"""
    if 'user_type' not in session or session['user_type'] != 'student':
        return redirect(url_for('index'))
    
    student_id = session['user_id']
    student_results = []
    
    # Get all results where this student is a winner
    for result in results_db:
        for winner in result['winners']:
            if winner['student_id'] == student_id:
                student_result = {
                    'event_name': result['event_name'],
                    'category': result['category'],
                    'date': result['date'],
                    'position': winner['position'],
                    'chest_number': winner['chest_number'],
                    'timestamp': result['timestamp']
                }
                student_results.append(student_result)
    
    # Sort by date
    student_results.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return render_template('my_results.html', results=student_results)

@app.route('/notifications')
def notifications():
    if 'user_type' not in session:
        return redirect(url_for('index'))
    
    # Get notifications for the user
    user_notifications = [n for n in notifications_db if n.get('user_id') == session.get('user_id') or n.get('user_id') is None]
    return render_template('notifications.html', notifications=user_notifications)

if __name__ == '__main__':
    app.run(debug=True)
