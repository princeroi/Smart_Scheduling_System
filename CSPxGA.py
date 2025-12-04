

import json
import sys
import random
from collections import defaultdict



FIRST_BREAK_RANGE_START = 10
FIRST_BREAK_RANGE_END = 13
SECOND_BREAK_RANGE_START = 17
SECOND_BREAK_RANGE_END = 18
BREAK_DURATION = 1

DAY_MAPPING = {
    'MON': 'Mon', 'MONDAY': 'Mon', 'Mon': 'Mon',
    'TUE': 'Tue', 'TUESDAY': 'Tue', 'Tue': 'Tue',
    'WED': 'Wed', 'WEDNESDAY': 'Wed', 'Wed': 'Wed',
    'THU': 'Thu', 'THURSDAY': 'Thu', 'Thu': 'Thu',
    'FRI': 'Fri', 'FRIDAY': 'Fri', 'Fri': 'Fri',
    'SAT': 'Sat', 'SATURDAY': 'Sat', 'Sat': 'Sat'
}

TIME_SLOTS = ["8AM", "9AM", "10AM", "11AM", "12PM", "1PM", "2PM", "3PM", "4PM", "5PM", "6PM", "7PM"]
TIME_MAP = {
    "8AM": 8, "9AM": 9, "10AM": 10, "11AM": 11, 
    "12PM": 12, "1PM": 13, "2PM": 14, "3PM": 15, 
    "4PM": 16, "5PM": 17, "6PM": 18, "7PM": 19
}

POPULATION_SIZE = 25
GENERATIONS = 50
CSP_INITIAL_POPULATION = 15
ELITE_SIZE = 3
MUTATION_RATE = 0.2

title = ""
firstbreak = 0
secondbreak = 0
teacher_load = []
teacher_availability = []
courses = []
rooms_list = []
sections_list = []
days = []
time_slots = TIME_SLOTS
time_map = TIME_MAP


def calculate_expected_schedules():
    total_expected = 0
    expected_by_section = {}

    for sec in sections_list:
        section_expected = 0
        for course_code in sec['courses']:
            course_obj = next((c for c in courses if c['code'] == course_code), None)
            if course_obj:
                num_sessions = course_obj['days']
                section_expected += num_sessions
        expected_by_section[sec['name']] = section_expected
        total_expected += section_expected

    return total_expected, expected_by_section


def analyze_schedule_completeness(schedule):
    _, expected_by_section = calculate_expected_schedules()

    actual_by_section = {}
    created_courses_by_section = {}

    for sec in sections_list:
        actual_by_section[sec['name']] = 0
        created_courses_by_section[sec['name']] = {}

        for course_code in sec['courses']:
            course_classes = [g for g in schedule if g['section'] == sec['name'] and g['course'] == course_code]
            actual_count = len(course_classes)
            actual_by_section[sec['name']] += actual_count
            created_courses_by_section[sec['name']][course_code] = actual_count

    return expected_by_section, actual_by_section, created_courses_by_section


def get_hours_per_session(course):
    return course["units"] / course["days"]


def times_overlap(start1, dur1, start2, dur2):
    end1 = time_map[start1] + dur1
    end2 = time_map[start2] + dur2
    return (time_map[start1] < end2) and (time_map[start2] < end1)


def calculate_end_time(start_time, duration):
    start_hour = time_map[start_time]
    end_hour_float = start_hour + duration
    end_hour = int(end_hour_float)
    end_min = int((end_hour_float - end_hour) * 60)
    
    if end_min > 0:
        if end_hour < 12:
            return f"{end_hour}:{end_min:02d}AM"
        elif end_hour == 12:
            return f"12:{end_min:02d}PM"
        else:
            return f"{end_hour-12}:{end_min:02d}PM"
    else:
        if end_hour < 12:
            return f"{end_hour}AM"
        elif end_hour == 12:
            return "12PM"
        else:
            return f"{end_hour-12}PM"


def calculate_schedule_diversity(population):
    if not population:
        return 0.0

    schedule_signatures = []
    for schedule in population:
        signature = tuple(sorted([(g['section'], g['course'], g['day'], g['time']) for g in schedule]))
        schedule_signatures.append(signature)

    unique_schedules = len(set(schedule_signatures))
    return unique_schedules / len(population)


def get_all_teacher_ids():
    return list(set([t['teacher_id'] for t in teacher_load]))


def get_teacher_info(teacher_id):
    load_info = next((l for l in teacher_load if l['teacher_id'] == teacher_id), None)
    if not load_info:
        return None

    availability_info = next((a for a in teacher_availability if a['teacher_id'] == teacher_id), None)

    availability = {}
    if availability_info:
        for day in days:
            if day in availability_info:
                availability[day] = availability_info[day]

    return {
        'id': teacher_id,
        'name': load_info.get('teacher_name', teacher_id),
        'courses': load_info['courses'],
        'max_units': load_info['max_units'],
        'status': availability_info['status'] if availability_info else 'FULL-TIME',
        'availability': availability
    }


def get_all_teachers_info():
    teacher_ids = get_all_teacher_ids()
    return [get_teacher_info(tid) for tid in teacher_ids]


def is_teacher_available(teacher_info, day, start_time, duration):
    if day not in teacher_info['availability']:
        return False

    available_hours = teacher_info['availability'][day]

    class_start = time_map[start_time]
    class_end = class_start + duration

    required_hours = []
    current_hour = class_start
    while current_hour < class_end:
        required_hours.append(int(current_hour))
        current_hour += 1

    return all(hour in available_hours for hour in required_hours)


def teacher_can_teach_course(teacher_id, course_code):

    teacher_info = next((t for t in teacher_load if t['teacher_id'] == teacher_id), None)
    if not teacher_info:
        return False
    return course_code in teacher_info['courses']


def has_continuous_schedule(schedule, entity_type, entity_id, day, start_hour, end_hour):
    classes = [g for g in schedule if g[entity_type] == entity_id and g['day'] == day]
    if not classes:
        return False

    covered_hours = set()
    for g in classes:
        class_start = time_map[g['time']]
        class_end = class_start + g['duration']
        for h in range(int(class_start), int(class_end)):
            covered_hours.add(h)

    required_hours = set(range(start_hour, end_hour))
    return required_hours.issubset(covered_hours)


def get_break_assignments(schedule):
    break_assignments = {}
    teachers_info = get_all_teachers_info()

    for day in days:
        used_first_breaks = set()
        used_second_breaks = set()

        for sec in sections_list:
            sec_classes = [g for g in schedule if g['section'] == sec['name'] and g['day'] == day]
            if not sec_classes:
                continue

            valid_first_breaks = []
            for break_start in range(FIRST_BREAK_RANGE_START, FIRST_BREAK_RANGE_END):
                has_conflict = False
                for g in sec_classes:
                    if times_overlap(f"{break_start}{'AM' if break_start < 12 else 'PM'}",
                                   BREAK_DURATION, g['time'], g['duration']):
                        has_conflict = True
                        break
                if not has_conflict:
                    valid_first_breaks.append(break_start)

            if valid_first_breaks:
                unused_breaks = [b for b in valid_first_breaks if b not in used_first_breaks]
                chosen_break = random.choice(unused_breaks) if unused_breaks else random.choice(valid_first_breaks)
                break_assignments[('section', sec['name'], day, 'first')] = chosen_break
                used_first_breaks.add(chosen_break)
            else:
                break_assignments[('section', sec['name'], day, 'first')] = random.choice(range(FIRST_BREAK_RANGE_START, FIRST_BREAK_RANGE_END))

            if has_continuous_schedule(schedule, 'section', sec['name'], day, 13, 17):
                valid_second_breaks = []
                for break_start in range(SECOND_BREAK_RANGE_START, SECOND_BREAK_RANGE_END):
                    has_conflict = False
                    for g in sec_classes:
                        if times_overlap(f"{break_start-12}PM", BREAK_DURATION, g['time'], g['duration']):
                            has_conflict = True
                            break
                    if not has_conflict:
                        valid_second_breaks.append(break_start)

                if valid_second_breaks:
                    unused_breaks = [b for b in valid_second_breaks if b not in used_second_breaks]
                    chosen_break = random.choice(unused_breaks) if unused_breaks else random.choice(valid_second_breaks)
                    break_assignments[('section', sec['name'], day, 'second')] = chosen_break
                    used_second_breaks.add(chosen_break)
                else:
                    break_assignments[('section', sec['name'], day, 'second')] = random.choice(range(SECOND_BREAK_RANGE_START, SECOND_BREAK_RANGE_END))

        for tchr_info in teachers_info:
            tchr_classes = [g for g in schedule if g['teacher'] == tchr_info['id'] and g['day'] == day]
            if not tchr_classes:
                continue

            valid_first_breaks = []
            for break_start in range(FIRST_BREAK_RANGE_START, FIRST_BREAK_RANGE_END):
                has_conflict = False
                for g in tchr_classes:
                    if times_overlap(f"{break_start}{'AM' if break_start < 12 else 'PM'}",
                                   BREAK_DURATION, g['time'], g['duration']):
                        has_conflict = True
                        break
                if not has_conflict:
                    valid_first_breaks.append(break_start)

            if valid_first_breaks:
                unused_breaks = [b for b in valid_first_breaks if b not in used_first_breaks]
                chosen_break = random.choice(unused_breaks) if unused_breaks else random.choice(valid_first_breaks)
                break_assignments[('teacher', tchr_info['id'], day, 'first')] = chosen_break
                used_first_breaks.add(chosen_break)
            else:
                break_assignments[('teacher', tchr_info['id'], day, 'first')] = random.choice(range(FIRST_BREAK_RANGE_START, FIRST_BREAK_RANGE_END))

            if has_continuous_schedule(schedule, 'teacher', tchr_info['id'], day, 13, 17):
                valid_second_breaks = []
                for break_start in range(SECOND_BREAK_RANGE_START, SECOND_BREAK_RANGE_END):
                    has_conflict = False
                    for g in tchr_classes:
                        if times_overlap(f"{break_start-12}PM", BREAK_DURATION, g['time'], g['duration']):
                            has_conflict = True
                            break
                    if not has_conflict:
                        valid_second_breaks.append(break_start)

                if valid_second_breaks:
                    unused_breaks = [b for b in valid_second_breaks if b not in used_second_breaks]
                    chosen_break = random.choice(unused_breaks) if unused_breaks else random.choice(valid_second_breaks)
                    break_assignments[('teacher', tchr_info['id'], day, 'second')] = chosen_break
                    used_second_breaks.add(chosen_break)
                else:
                    break_assignments[('teacher', tchr_info['id'], day, 'second')] = random.choice(range(SECOND_BREAK_RANGE_START, SECOND_BREAK_RANGE_END))

    return break_assignments


def get_valid_rooms_for_course(course_obj, section_name):
    if course_obj['type'] == 'Online':
        return ['ONLINE']
    
    section = next((s for s in sections_list if s['name'] == section_name), None)
    if not section:
        return []
    
    student_count = section.get('student_count', 30)
    
    valid_rooms = [
        r['room'] for r in rooms_list 
        if r['type'] == course_obj['type'] and r.get('capacity', 40) >= student_count
    ]
    
    if not valid_rooms:
        valid_rooms = [r['room'] for r in rooms_list if r['type'] == course_obj['type']]
    
    return valid_rooms


def get_random_valid_room(course_obj, section_name):

    valid_rooms = get_valid_rooms_for_course(course_obj, section_name)
    
    if valid_rooms:
        return random.choice(valid_rooms)
    
    if course_obj['type'] == 'Online':
        return 'ONLINE'
    
    return 'NO ROOM'

def generate_csp_schedule():
    teachers_info = get_all_teachers_info()
    
    if not teachers_info or not days:
        return None
    
    schedule = []
    
    tasks = []
    for sec in sections_list:
        for course_code in sec['courses']:
            course_obj = next((c for c in courses if c['code'] == course_code), None)
            if not course_obj:
                continue
            
            qualified_teachers = [t for t in teachers_info if course_code in t['courses']]
            
            if not qualified_teachers:
                num_sessions = course_obj['days']
                for session in range(num_sessions):
                    schedule.append({
                        'section': sec['name'],
                        'course': course_code,
                        'teacher': 'NO AVAILABLE TEACHER',
                        'room': 'ONLINE' if course_obj['type'] == 'Online' else 'NO ROOM',
                        'day': days[session % len(days)],
                        'time': time_slots[session % len(time_slots)],
                        'duration': get_hours_per_session(course_obj)
                    })
                continue

            num_sessions = course_obj['days']
            for session in range(num_sessions):
                tasks.append({
                    'section': sec['name'],
                    'course': course_code,
                    'session': session,
                    'course_obj': course_obj,
                    'qualified_teachers': qualified_teachers
                })
n
    random.shuffle(tasks)

    for task in tasks:
        assignment = find_valid_assignment(task, schedule, teachers_info)
        if assignment:
            schedule.append(assignment)
        else:
            schedule.append({
                'section': task['section'],
                'course': task['course'],
                'teacher': task['qualified_teachers'][0]['id'],
                'room': get_random_valid_room(task['course_obj'], task['section']),
                'day': random.choice(days),
                'time': random.choice(time_slots),
                'duration': get_hours_per_session(task['course_obj'])
            })
    
    return schedule if schedule else None


def find_valid_assignment(task, current_schedule, teachers_info):
    course_obj = task['course_obj']
    duration = get_hours_per_session(course_obj)
    section_name = task['section']

    valid_rooms = get_valid_rooms_for_course(course_obj, section_name)
    if not valid_rooms:
        valid_rooms = ['ONLINE' if course_obj['type'] == 'Online' else 'NO ROOM']

    random.shuffle(valid_rooms)

    teachers = task['qualified_teachers'].copy()
    random.shuffle(teachers)
    
    for teacher in teachers:
        teacher_info = next((t for t in teachers_info if t['id'] == teacher['id']), None)
        if not teacher_info:
            continue

        available_days = list(days)
        random.shuffle(available_days)
        
        for day in available_days:
            if day not in teacher_info['availability']:
                continue
            
            available_hours = teacher_info['availability'][day]
            
            time_slots_shuffled = time_slots.copy()
            random.shuffle(time_slots_shuffled)
            
            for time_slot in time_slots_shuffled:
                if not is_teacher_available(teacher_info, day, time_slot, duration):
                    continue
                
                for room in valid_rooms:
                    assignment = {
                        'section': section_name,
                        'course': task['course'],
                        'teacher': teacher['id'],
                        'room': room,
                        'day': day,
                        'time': time_slot,
                        'duration': duration
                    }
                    
                    if is_assignment_valid(assignment, current_schedule, teacher_info):
                        return assignment
    
    return None


def is_assignment_valid(assignment, current_schedule, teacher_info):
    for scheduled in current_schedule:
        if (scheduled['teacher'] == assignment['teacher'] and 
            scheduled['day'] == assignment['day']):
            if times_overlap(scheduled['time'], scheduled['duration'], 
                           assignment['time'], assignment['duration']):
                return False
ts
    for scheduled in current_schedule:
        if (scheduled['section'] == assignment['section'] and 
            scheduled['day'] == assignment['day']):
            if times_overlap(scheduled['time'], scheduled['duration'], 
                           assignment['time'], assignment['duration']):
                return False
    if assignment['room'] not in ['ONLINE', 'NO ROOM']:
        for scheduled in current_schedule:
            if (scheduled['room'] == assignment['room'] and 
                scheduled['day'] == assignment['day'] and
                scheduled['room'] not in ['ONLINE', 'NO ROOM']):
                if times_overlap(scheduled['time'], scheduled['duration'], 
                               assignment['time'], assignment['duration']):
                    return False
    section_day_hours = sum(
        s['duration'] for s in current_schedule 
        if s['section'] == assignment['section'] and s['day'] == assignment['day']
    )
    if section_day_hours + assignment['duration'] > 10:
        return False
    teacher_total_hours = sum(
        s['duration'] for s in current_schedule 
        if s['teacher'] == assignment['teacher']
    )
    if teacher_total_hours + assignment['duration'] > teacher_info['max_units']:
        return False
    if assignment['room'] == 'ONLINE':
        for scheduled in current_schedule:
            if (scheduled['room'] == 'ONLINE' and 
                scheduled['day'] == assignment['day'] and 
                scheduled['time'] == assignment['time']):
                return False
    
    return True

def detect_conflicts(schedule):
    """Enhanced conflict detection with detailed reporting"""
    conflicts = []
    break_assignments = get_break_assignments(schedule)
    teachers_info = get_all_teachers_info()

    for g in schedule:
        if g['teacher'] == 'NO AVAILABLE TEACHER':
            conflicts.append({
                'type': 'no_available_teacher',
                'section': g['section'],
                'course': g['course'],
                'day': g['day'],
                'time': g['time'],
                'message': f"No teacher available to teach {g['course']} for section {g['section']} on {g['day']} at {g['time']}"
            })
        elif not teacher_can_teach_course(g['teacher'], g['course']):
            end_time = calculate_end_time(g['time'], g['duration'])
            conflicts.append({
                'type': 'teacher_course_mismatch',
                'teacher': g['teacher'],
                'course': g['course'],
                'section': g['section'],
                'day': g['day'],
                'time': g['time'],
                'class_time': f"{g['time']}-{end_time}",
                'message': f"Teacher {g['teacher']} is assigned to teach {g['course']} for section {g['section']}, but this course is not in their teaching load"
            })

    for g in schedule:
        if g['teacher'] == 'NO AVAILABLE TEACHER':
            continue
        teacher_info = next((t for t in teachers_info if t['id'] == g['teacher']), None)
        if not teacher_info:
            continue
        if not is_teacher_available(teacher_info, g['day'], g['time'], g['duration']):
            end_time = calculate_end_time(g['time'], g['duration'])
            if g['day'] in teacher_info['availability']:
                avail_hours = teacher_info['availability'][g['day']]
                avail_str = f"{min(avail_hours)}:00-{max(avail_hours)+1}:00" if avail_hours else "Not Available"
            else:
                avail_str = "Not Available"
            conflicts.append({
                'type': 'teacher_availability',
                'teacher': g['teacher'],
                'day': g['day'],
                'course': g['course'],
                'section': g['section'],
                'time': g['time'],
                'class_time': f"{g['time']}-{end_time}",
                'teacher_availability': avail_str,
                'message': f"Teacher {g['teacher']} availability violated: {g['course']} ({g['section']}) scheduled {g['day']} {g['time']}-{end_time}, but teacher available only {avail_str}"
            })

    for key, break_start in break_assignments.items():
        entity_type, entity_id, day, break_type = key
        break_end = break_start + BREAK_DURATION

        for g in schedule:
            if g['day'] != day:
                continue
            if entity_type == 'section' and g['section'] != entity_id:
                continue
            if entity_type == 'teacher' and g['teacher'] != entity_id:
                continue

            class_start = time_map[g['time']]
            class_end = class_start + g['duration']

            if (class_start < break_end) and (class_end > break_start):
                break_time_str = f"{break_start}:00-{break_end}:00"
                end_time_str = calculate_end_time(g['time'], g['duration'])
                conflicts.append({
                    'type': 'break_violation',
                    'entity_type': entity_type,
                    'entity_id': entity_id,
                    'day': day,
                    'time': g['time'],
                    'break_type': break_type,
                    'break_time': break_time_str,
                    'course': g['course'],
                    'class_time': f"{g['time']}-{end_time_str}",
                    'section': g['section'],
                    'teacher': g['teacher'],
                    'message': f"{entity_type.capitalize()} {entity_id} {break_type} break ({break_time_str}) violated by {g['course']} on {day} at {g['time']}-{end_time_str}"
                })

    return conflicts  

def detect_conflicts_part_b(schedule, conflicts):
    """
    Continuation of conflict detection - overlaps and resource conflicts
    This should be called within detect_conflicts() after Part A checks
    """
    teachers_info = get_all_teachers_info()

    for i, g1 in enumerate(schedule):
        for j, g2 in enumerate(schedule):
            if i >= j:
                continue

            if g1['teacher'] == 'NO AVAILABLE TEACHER' or g2['teacher'] == 'NO AVAILABLE TEACHER':
                continue

            if g1["teacher"] == g2["teacher"] and g1["day"] == g2["day"]:
                if times_overlap(g1["time"], g1["duration"], g2["time"], g2["duration"]):
                    end1 = calculate_end_time(g1['time'], g1['duration'])
                    end2 = calculate_end_time(g2['time'], g2['duration'])
                    conflicts.append({
                        'type': 'teacher_overlap',
                        'teacher': g1['teacher'],
                        'day': g1['day'],
                        'time': g1['time'],
                        'class1': {'section': g1['section'], 'course': g1['course'],
                                  'time': g1['time'], 'end': end1, 'room': g1['room']},
                        'class2': {'section': g2['section'], 'course': g2['course'],
                                  'time': g2['time'], 'end': end2, 'room': g2['room']},
                        'message': f"Teacher {g1['teacher']} overlap on {g1['day']}: {g1['section']} {g1['course']} ({g1['time']}-{end1}) vs {g2['section']} {g2['course']} ({g2['time']}-{end2})"
                    })

            if g1["room"] == g2["room"] and g1["room"] != "ONLINE" and g1["room"] != "NO ROOM" and g1["day"] == g2["day"]:
                if times_overlap(g1["time"], g1["duration"], g2["time"], g2["duration"]):
                    end1 = calculate_end_time(g1['time'], g1['duration'])
                    end2 = calculate_end_time(g2['time'], g2['duration'])
                    conflicts.append({
                        'type': 'room_overlap',
                        'room': g1['room'],
                        'day': g1['day'],
                        'time': g1['time'],
                        'class1': {'section': g1['section'], 'course': g1['course'],
                                  'time': g1['time'], 'end': end1, 'teacher': g1['teacher']},
                        'class2': {'section': g2['section'], 'course': g2['course'],
                                  'time': g2['time'], 'end': end2, 'teacher': g2['teacher']},
                        'message': f"Room {g1['room']} overlap on {g1['day']}: {g1['section']} {g1['course']} ({g1['time']}-{end1}) vs {g2['section']} {g2['course']} ({g2['time']}-{end2})"
                    })

            if g1["section"] == g2["section"] and g1["day"] == g2["day"]:
                if times_overlap(g1["time"], g1["duration"], g2["time"], g2["duration"]):
                    end1 = calculate_end_time(g1['time'], g1['duration'])
                    end2 = calculate_end_time(g2['time'], g2['duration'])
                    conflicts.append({
                        'type': 'section_overlap',
                        'section': g1['section'],
                        'day': g1['day'],
                        'time': g1['time'],
                        'class1': {'course': g1['course'], 'time': g1['time'], 'end': end1,
                                  'teacher': g1['teacher'], 'room': g1['room']},
                        'class2': {'course': g2['course'], 'time': g2['time'], 'end': end2,
                                  'teacher': g2['teacher'], 'room': g2['room']},
                        'message': f"Section {g1['section']} overlap on {g1['day']}: {g1['course']} ({g1['time']}-{end1}, T:{g1['teacher']}, R:{g1['room']}) vs {g2['course']} ({g2['time']}-{end2}, T:{g2['teacher']}, R:{g2['room']})"
                    })

    online_courses = [g for g in schedule if g['room'] == 'ONLINE']
    for i, o1 in enumerate(online_courses):
        for o2 in online_courses[i+1:]:
            if o1['day'] == o2['day'] and o1['time'] == o2['time']:
                end1 = calculate_end_time(o1['time'], o1['duration'])
                end2 = calculate_end_time(o2['time'], o2['duration'])
                conflicts.append({
                    'type': 'online_overlap',
                    'day': o1['day'],
                    'time': o1['time'],
                    'class1': {'section': o1['section'], 'course': o1['course'],
                              'teacher': o1['teacher'], 'end': end1},
                    'class2': {'section': o2['section'], 'course': o2['course'],
                              'teacher': o2['teacher'], 'end': end2},
                    'message': f"Online courses conflict on {o1['day']} at {o1['time']}-{end1}: {o1['section']} {o1['course']} (T:{o1['teacher']}) vs {o2['section']} {o2['course']} (T:{o2['teacher']})"
                })

    for tchr_info in teachers_info:
        for day in days:
            online_courses = [g for g in schedule if g["teacher"] == tchr_info["id"] and g["day"] == day and g["room"] == "ONLINE"]
            offline_courses = [g for g in schedule if g["teacher"] == tchr_info["id"] and g["day"] == day and g["room"] != "ONLINE" and g["room"] != "NO ROOM"]
            if online_courses and offline_courses:
                online_list = ', '.join([f"{g['course']} ({g['time']}-{calculate_end_time(g['time'], g['duration'])})" for g in online_courses])
                offline_list = ', '.join([f"{g['course']} ({g['time']}-{calculate_end_time(g['time'], g['duration'])}, R:{g['room']})" for g in offline_courses])
                conflicts.append({
                    'type': 'teacher_online_offline_mix',
                    'teacher': tchr_info['id'],
                    'day': day,
                    'time': online_courses[0]['time'],
                    'online_courses': online_courses,
                    'offline_courses': offline_courses,
                    'message': f"Teacher {tchr_info['id']} has online + offline courses on {day}: Online=[{online_list}], Offline=[{offline_list}]"
                })

    for sec in sections_list:
        for day in days:
            online_courses = [g for g in schedule if g["section"] == sec["name"] and g["day"] == day and g["room"] == "ONLINE"]
            offline_courses = [g for g in schedule if g["section"] == sec["name"] and g["day"] == day and g["room"] != "ONLINE" and g["room"] != "NO ROOM"]
            if online_courses and offline_courses:
                online_list = ', '.join([f"{g['course']} ({g['time']}-{calculate_end_time(g['time'], g['duration'])}, T:{g['teacher']})" for g in online_courses])
                offline_list = ', '.join([f"{g['course']} ({g['time']}-{calculate_end_time(g['time'], g['duration'])}, T:{g['teacher']}, R:{g['room']})" for g in offline_courses])
                conflicts.append({
                    'type': 'section_online_offline_mix',
                    'section': sec['name'],
                    'day': day,
                    'time': online_courses[0]['time'],
                    'online_courses': online_courses,
                    'offline_courses': offline_courses,
                    'message': f"Section {sec['name']} has online + offline courses on {day}: Online=[{online_list}], Offline=[{offline_list}]"
                })

    return conflicts

def detect_conflicts_part_c(schedule, conflicts):
    """
    Final part of conflict detection - capacity and limits
    This should be called within detect_conflicts() after Part B
    """
    teachers_info = get_all_teachers_info()

    for sec in sections_list:
        for day in days:
            sec_classes = [g for g in schedule if g['section'] == sec['name'] and g['day'] == day]
            total_hours = sum(g['duration'] for g in sec_classes)
            if total_hours > 10:
                class_list = ', '.join([f"{g['course']} ({g['time']}-{calculate_end_time(g['time'], g['duration'])}, {g['duration']}h)" for g in sec_classes])
                for g in sec_classes:
                    conflicts.append({
                        'type': 'section_daily_hours_exceeded',
                        'section': sec['name'],
                        'day': day,
                        'time': g['time'],
                        'total_hours': total_hours,
                        'course': g['course'],
                        'classes': sec_classes,
                        'message': f"Section {sec['name']} exceeds 10 hours on {day}: {total_hours:.1f} hours - Classes: [{class_list}]"
                    })

    for tchr_info in teachers_info:
        tchr_classes = [g for g in schedule if g['teacher'] == tchr_info['id']]
        total_hours = sum(g['duration'] for g in tchr_classes)
        if total_hours > tchr_info['max_units']:
            class_list = ', '.join([f"{g['course']} ({g['day']} {g['time']}-{calculate_end_time(g['time'], g['duration'])}, {g['duration']}h)" for g in tchr_classes])
            for g in tchr_classes:
                conflicts.append({
                    'type': 'teacher_max_units_exceeded',
                    'teacher': tchr_info['id'],
                    'day': g['day'],
                    'time': g['time'],
                    'total_hours': total_hours,
                    'max_units': tchr_info['max_units'],
                    'course': g['course'],
                    'classes': tchr_classes,
                    'message': f"Teacher {tchr_info['id']} exceeds max units: {total_hours:.1f}/{tchr_info['max_units']} hours - Classes: [{class_list}]"
                })

    for g in schedule:
        if g['room'] == 'ONLINE' or g['room'] == 'NO ROOM':
            continue
            
        section = next((s for s in sections_list if s['name'] == g['section']), None)
        room = next((r for r in rooms_list if r['room'] == g['room']), None)
        
        if section and room:
            student_count = section.get('student_count', 0)
            room_capacity = room.get('capacity', 0)
            
            if student_count > room_capacity:
                conflicts.append({
                    'type': 'room_capacity_exceeded',
                    'section': g['section'],
                    'room': g['room'],
                    'day': g['day'],
                    'time': g['time'],
                    'course': g['course'],
                    'student_count': student_count,
                    'room_capacity': room_capacity,
                    'overage': student_count - room_capacity,
                    'message': f"Room {g['room']} capacity exceeded: {student_count} students in room with {room_capacity} capacity for {g['section']} {g['course']} on {g['day']} at {g['time']}"
                })

    for g in schedule:
        if g['room'] == 'ONLINE' or g['room'] == 'NO ROOM':
            continue
            
        course = next((c for c in courses if c['code'] == g['course']), None)
        room = next((r for r in rooms_list if r['room'] == g['room']), None)
        
        if course and room:
            course_type = course.get('type', 'LECTURE')
            room_type = room.get('type', 'LECTURE')
            
            if course_type != room_type:
                end_time = calculate_end_time(g['time'], g['duration'])
                conflicts.append({
                    'type': 'room_type_mismatch',
                    'section': g['section'],
                    'course': g['course'],
                    'room': g['room'],
                    'day': g['day'],
                    'time': g['time'],
                    'class_time': f"{g['time']}-{end_time}",
                    'course_type': course_type,
                    'room_type': room_type,
                    'message': f"Room type mismatch: {g['course']} (type: {course_type}) assigned to {g['room']} (type: {room_type}) for {g['section']} on {g['day']} at {g['time']}-{end_time}"
                })

    return conflicts

def detect_conflicts(schedule):
    """Main conflict detection function - combines all parts"""
    conflicts = []
    break_assignments = get_break_assignments(schedule)
    teachers_info = get_all_teachers_info()

    for g in schedule:
        if g['teacher'] == 'NO AVAILABLE TEACHER':
            conflicts.append({
                'type': 'no_available_teacher',
                'section': g['section'],
                'course': g['course'],
                'day': g['day'],
                'time': g['time'],
                'message': f"No teacher available to teach {g['course']} for section {g['section']} on {g['day']} at {g['time']}"
            })
        elif not teacher_can_teach_course(g['teacher'], g['course']):
            end_time = calculate_end_time(g['time'], g['duration'])
            conflicts.append({
                'type': 'teacher_course_mismatch',
                'teacher': g['teacher'],
                'course': g['course'],
                'section': g['section'],
                'day': g['day'],
                'time': g['time'],
                'message': f"Teacher {g['teacher']} is assigned to teach {g['course']} but this course is not in their teaching load"
            })

    conflicts = detect_conflicts_part_b(schedule, conflicts)
    conflicts = detect_conflicts_part_c(schedule, conflicts)
    
    return conflicts

def calculate_fitness(schedule):
    """Enhanced fitness function with better weight distribution and room balance"""
    if not schedule:
        return -999999
    
    score = 0
    teachers_info = get_all_teachers_info()

    conflicts = detect_conflicts(schedule)
    conflict_types = {}
    for c in conflicts:
        ctype = c['type']
        if ctype not in conflict_types:
            conflict_types[ctype] = 0
        conflict_types[ctype] += 1

    score -= conflict_types.get('teacher_overlap', 0) * 2000
    score -= conflict_types.get('section_overlap', 0) * 2000
    score -= conflict_types.get('room_overlap', 0) * 1500
    score -= conflict_types.get('teacher_availability', 0) * 2500
    score -= conflict_types.get('online_overlap', 0) * 1500
    score -= conflict_types.get('break_violation', 0) * 800
    score -= conflict_types.get('teacher_online_offline_mix', 0) * 500
    score -= conflict_types.get('section_online_offline_mix', 0) * 500
    score -= conflict_types.get('section_daily_hours_exceeded', 0) * 1200
    score -= conflict_types.get('teacher_max_units_exceeded', 0) * 1200
    score -= conflict_types.get('room_capacity_exceeded', 0) * 1800
    score -= conflict_types.get('teacher_course_mismatch', 0) * 3000
    score -= conflict_types.get('no_available_teacher', 0) * 5000

    for g in schedule:
        if g['teacher'] == 'NO AVAILABLE TEACHER':
            continue
        teacher_info = next((t for t in teachers_info if t['id'] == g['teacher']), None)
        if teacher_info and is_teacher_available(teacher_info, g['day'], g['time'], g['duration']):
            score += 100

    break_assignments = get_break_assignments(schedule)
    for key, break_start in break_assignments.items():
        entity_type, entity_id, day, break_type = key
        break_end = break_start + BREAK_DURATION

        has_violation = False
        for g in schedule:
            if g['day'] != day:
                continue
            if entity_type == 'section' and g['section'] != entity_id:
                continue
            if entity_type == 'teacher' and g['teacher'] != entity_id:
                continue

            class_start = time_map[g['time']]
            class_end = class_start + g['duration']

            if (class_start < break_end) and (class_end > break_start):
                has_violation = True
                break

        if not has_violation:
            score += 150

    time_usage = {slot: sum(1 for g in schedule if g['time'] == slot) for slot in time_slots}
    if time_usage:
        time_std = (max(time_usage.values()) - min(time_usage.values()))
        score -= time_std * 15

    teacher_hours = {t['id']: 0 for t in teachers_info}
    for g in schedule:
        if g['teacher'] != 'NO AVAILABLE TEACHER':
            teacher_hours[g['teacher']] += g['duration']
    if teacher_hours:
        workload_values = list(teacher_hours.values())
        if max(workload_values) > 0:
            workload_diff = max(workload_values) - min(workload_values)
            score -= workload_diff * 30

    for sec in sections_list:
        for day in days:
            day_classes = sorted([g for g in schedule if g['section'] == sec['name'] and g['day'] == day],
                                key=lambda x: time_map[x['time']])
            for i in range(len(day_classes) - 1):
                current_end = time_map[day_classes[i]['time']] + day_classes[i]['duration']
                next_start = time_map[day_classes[i+1]['time']]
                gap = next_start - current_end
                if gap == 0:
                    score += 20
                elif gap == 1:
                    score += 10
                elif gap > 2:
                    score -= gap * 5

    for g in schedule:
        hour = time_map[g['time']]
        if hour <= 10:
            score += 5
        elif hour >= 17:
            score -= 3

    for sec in sections_list:
        for course_code in sec['courses']:
            course_classes = [g for g in schedule if g['section'] == sec['name'] and g['course'] == course_code]
            unique_days = len(set(g['day'] for g in course_classes))
            course_obj = next((c for c in courses if c['code'] == course_code), None)
            if course_obj and unique_days == course_obj['days']:
                score += 25

    room_usage = {}
    for g in schedule:
        if g['room'] not in ['ONLINE', 'NO ROOM']:
            room_usage[g['room']] = room_usage.get(g['room'], 0) + 1

    if len(room_usage) > 1:
        usage_values = list(room_usage.values())
        room_balance = max(usage_values) - min(usage_values)
        score -= room_balance * 10

        unique_rooms_used = len(room_usage)
        total_available_rooms = len([r for r in rooms_list if r['type'] != 'Online'])
        if total_available_rooms > 0:
            usage_ratio = unique_rooms_used / total_available_rooms
            score += int(usage_ratio * 100)

    return score


def run_genetic_algorithm():
    """
    Main genetic algorithm loop
    Returns: (best_schedule, best_fitness, all_generation_bests)
    """
    population = []

    print("Generating initial population using CSP...")
    sys.stdout.flush()

    for i in range(CSP_INITIAL_POPULATION):
        print(f"Generating CSP schedule {i+1}/{CSP_INITIAL_POPULATION}...")
        sys.stdout.flush()
        csp_schedule = generate_csp_schedule()
        if csp_schedule:
            population.append(csp_schedule)
            print(f"Successfully generated schedule {i+1}")
            sys.stdout.flush()
        else:
            print(f"Failed to generate schedule {i+1}")
            sys.stdout.flush()

    if len(population) == 0:
        print("No CSP schedules generated, creating fallback schedule...")
        sys.stdout.flush()
        fallback_schedule = create_fallback_schedule()
        if fallback_schedule:
            population.append(fallback_schedule)

    if len(population) < POPULATION_SIZE and len(population) > 0:
        attempts = 0
        max_attempts = POPULATION_SIZE * 3
        while len(population) < POPULATION_SIZE and attempts < max_attempts:
            if population:
                base = [dict(g) for g in random.choice(population)]
                for _ in range(random.randint(1, 3)):
                    if base:
                        gene = random.choice(base)
                        if gene['teacher'] != 'NO AVAILABLE TEACHER':
                            mutation_choice = random.random()
                            if mutation_choice < 0.4:
                                gene['time'] = random.choice(time_slots)
                            elif mutation_choice < 0.8:
                                gene['day'] = random.choice(days)
                            else:
                                gene['time'] = random.choice(time_slots)
                                gene['day'] = random.choice(days)
                population.append(base)
            attempts += 1

    if len(population) == 0:
        return None, float('-inf'), []

    all_generation_bests = []
    best_fitness_ever = float('-inf')
    stagnation_counter = 0

    print("Starting genetic algorithm optimization...")
    sys.stdout.flush()

    for g in range(GENERATIONS):
        scored = []
        for s in population:
            if s:
                fitness = calculate_fitness(s)
                scored.append((fitness, s))
        
        if not scored:
            break
        
        scored.sort(key=lambda x: x[0], reverse=True)
        generation_best = scored[0][1]
        generation_best_fitness = scored[0][0]

        diversity = calculate_schedule_diversity(population)

        all_generation_bests.append({
            'generation': g,
            'fitness': generation_best_fitness,
            'diversity': diversity,
            'schedule': [dict(entry) for entry in generation_best]
        })

        if g % 10 == 0 or g == GENERATIONS - 1:
            print(f"Generation {g}: Best fitness = {generation_best_fitness:.2f}, Diversity = {diversity:.2f}")
            sys.stdout.flush()

        if generation_best_fitness > best_fitness_ever:
            best_fitness_ever = generation_best_fitness
            stagnation_counter = 0
        else:
            stagnation_counter += 1

        elite = [s for f, s in scored[:ELITE_SIZE]]
        top_performers = [s for f, s in scored[:POPULATION_SIZE // 2]]
        new_pop = elite.copy()

        while len(new_pop) < POPULATION_SIZE:
            p1, p2 = random.sample(top_performers, 2)

            if len(p1) >= 4:
                point1 = random.randint(1, len(p1) // 3)
                point2 = random.randint(2 * len(p1) // 3, len(p1) - 1)
                child = p1[:point1] + p2[point1:point2] + p1[point2:]
            else:
                point = len(p1) // 2
                child = p1[:point] + p2[point:]

            child = [dict(g) for g in child]

            effective_mutation_rate = MUTATION_RATE
            if stagnation_counter > 10:
                effective_mutation_rate = min(0.4, MUTATION_RATE * 1.5)

            if random.random() < effective_mutation_rate and child:
                num_mutations = random.randint(1, 2)
                for _ in range(num_mutations):
                    gene = random.choice(child)
                    if gene['teacher'] != 'NO AVAILABLE TEACHER':
                        mutation_type = random.choice(['time', 'day', 'both', 'room'])
                        if mutation_type == 'time':
                            gene["time"] = random.choice(time_slots)
                        elif mutation_type == 'day':
                            gene["day"] = random.choice(days)
                        elif mutation_type == 'room':
                            course_obj = next((c for c in courses if c['code'] == gene['course']), None)
                            if course_obj and course_obj['type'] != 'Online':
                                section = next((s for s in sections_list if s['name'] == gene['section']), None)
                                if section:
                                    student_count = section.get('student_count', 30)
                                    valid_rooms = [
                                        r['room'] for r in rooms_list 
                                        if r['type'] == course_obj['type'] and r.get('capacity', 40) >= student_count
                                    ]
                                    if valid_rooms and gene['room'] in valid_rooms:
                                        other_rooms = [r for r in valid_rooms if r != gene['room']]
                                        if other_rooms:
                                            gene['room'] = random.choice(other_rooms)
                        else: 
                            gene["time"] = random.choice(time_slots)
                            gene["day"] = random.choice(days)

            new_pop.append(child)

        population = new_pop

    print("Finalizing best schedule...")
    sys.stdout.flush()
    
    if not all_generation_bests:
        if population:
            scored = [(calculate_fitness(s), s) for s in population if s]
            if scored:
                scored.sort(key=lambda x: x[0], reverse=True)
                all_generation_bests = [{
                    'generation': 0,
                    'fitness': scored[0][0],
                    'diversity': 0,
                    'schedule': [dict(entry) for entry in scored[0][1]]
                }]
            else:
                return None, float('-inf'), []
        else:
            return None, float('-inf'), []

    all_generation_bests.sort(key=lambda x: x['fitness'], reverse=True)
    final_best = all_generation_bests[0]
    best_schedule = [dict(entry) for entry in final_best['schedule']]
    best_fitness = final_best['fitness']

    return best_schedule, best_fitness, all_generation_bests


def create_fallback_schedule():
    """Create a basic fallback schedule when CSP fails"""
    fallback_schedule = []
    for sec in sections_list:
        for course_code in sec['courses']:
            course_obj = next((c for c in courses if c['code'] == course_code), None)
            if not course_obj:
                continue
            num_sessions = course_obj['days']
            
            qualified_teachers = [t for t in get_all_teachers_info() if course_code in t['courses']]
            
            if not qualified_teachers:
                teacher_id = 'NO AVAILABLE TEACHER'
                room_name = 'ONLINE' if course_obj['type'] == 'Online' else 'NO ROOM'
            else:
                teacher = qualified_teachers[0]
                teacher_id = teacher['id']
                
                section = next(s for s in sections_list if s['name'] == sec['name'])
                student_count = section.get('student_count', 30)
                
                appropriate_rooms = [
                    r for r in rooms_list 
                    if r['type'] == course_obj['type'] and r.get('capacity', 40) >= student_count
                ]
                
                if not appropriate_rooms:
                    appropriate_rooms = [r for r in rooms_list if r['type'] == course_obj['type']]
                
                room_name = random.choice(appropriate_rooms)['room'] if appropriate_rooms else rooms_list[0]['room']
            
            for session in range(num_sessions):
                fallback_schedule.append({
                    'section': sec['name'],
                    'course': course_code,
                    'teacher': teacher_id,
                    'room': room_name,
                    'day': days[session % len(days)],
                    'time': time_slots[session % len(time_slots)],
                    'duration': get_hours_per_session(course_obj)
                })
    
    return fallback_schedule if fallback_schedule else None


def prepare_output(best_schedule, best_fitness, all_generation_bests):
    """Prepare final JSON output"""
    
    final_conflicts = detect_conflicts(best_schedule)
    conflict_breakdown = {}
    for c in final_conflicts:
        ctype = c['type']
        if ctype not in conflict_breakdown:
            conflict_breakdown[ctype] = 0
        conflict_breakdown[ctype] += 1

    total_expected, expected_by_section = calculate_expected_schedules()
    expected, actual, created = analyze_schedule_completeness(best_schedule)
    completion_rate = (len(best_schedule) / total_expected * 100) if total_expected > 0 else 0

    conflicted_schedule = []
    conflict_free_schedule = []

    for entry in best_schedule:
        has_conflict = False
        entry_conflicts = []
        
        for conflict in final_conflicts:
            if (conflict.get('section') == entry['section'] and 
                conflict.get('course') == entry['course'] and
                conflict.get('day') == entry['day'] and
                conflict.get('time') == entry['time']):
                has_conflict = True
                entry_conflicts.append(conflict['message'])
        
        schedule_entry = {
            'section': entry['section'],
            'course': entry['course'],
            'teacher': entry['teacher'],
            'room': entry['room'],
            'day': entry['day'],
            'time': entry['time'],
            'end_time': calculate_end_time(entry['time'], entry['duration']),
            'duration': entry['duration']
        }
        
        if has_conflict:
            schedule_entry['conflicts'] = entry_conflicts
            conflicted_schedule.append(schedule_entry)
        else:
            conflict_free_schedule.append(schedule_entry)

    teacher_schedules = {}
    for teacher_info in get_all_teachers_info():
        tid = teacher_info['id']
        teacher_classes = [g for g in best_schedule if g['teacher'] == tid]
        
        if teacher_classes:
            teacher_schedules[tid] = {
                'teacher_id': tid,
                'teacher_name': teacher_info['name'],
                'classes': []
            }
            
            for g in teacher_classes:
                teacher_schedules[tid]['classes'].append({
                    'section': g['section'],
                    'course': g['course'],
                    'room': g['room'],
                    'day': g['day'],
                    'time': g['time'],
                    'end_time': calculate_end_time(g['time'], g['duration']),
                    'duration': g['duration']
                })

    section_schedules = {}
    for sec in sections_list:
        section_classes = [g for g in best_schedule if g['section'] == sec['name']]
        
        if section_classes:
            section_schedules[sec['name']] = {
                'section_name': sec['name'],
                'classes': []
            }
            
            for g in section_classes:
                section_schedules[sec['name']]['classes'].append({
                    'course': g['course'],
                    'teacher': g['teacher'],
                    'room': g['room'],
                    'day': g['day'],
                    'time': g['time'],
                    'end_time': calculate_end_time(g['time'], g['duration']),
                    'duration': g['duration']
                })

    room_schedules = {}
    for room in rooms_list:
        room_classes = [g for g in best_schedule if g['room'] == room['room']]
        
        if room_classes:
            room_schedules[room['room']] = {
                'room_name': room['room'],
                'room_type': room['type'],
                'classes': []
            }
            
            for g in room_classes:
                room_schedules[room['room']]['classes'].append({
                    'section': g['section'],
                    'course': g['course'],
                    'teacher': g['teacher'],
                    'day': g['day'],
                    'time': g['time'],
                    'end_time': calculate_end_time(g['time'], g['duration']),
                    'duration': g['duration']
                })

    output = {
        "title": title,
        "generated_schedule": conflict_free_schedule,
        "conflicted_schedule": conflicted_schedule,
        "expected_schedule": total_expected,
        "teacher_schedules": list(teacher_schedules.values()),
        "section_schedules": list(section_schedules.values()),
        "room_schedules": list(room_schedules.values()),
        "Number_of_Without_Conflict_Schedule": len(conflict_free_schedule),
        "Number_of_Conflicted": len(conflicted_schedule),
        "Total_Schedule": len(best_schedule),
        "Number_of_Expected_Schedule": total_expected,
        "statistics": {
            "completion_rate": round(completion_rate, 2),
            "final_fitness": round(best_fitness, 2),
            "diversity": round(all_generation_bests[0]['diversity'], 2) if all_generation_bests else 0,
            "generation": all_generation_bests[0]['generation'] if all_generation_bests else 0,
            "total_conflicts": len(final_conflicts),
            "conflict_summary": {
                "total_conflicts": len(final_conflicts),
                "conflict_breakdown": conflict_breakdown,
                "has_conflicts": len(final_conflicts) > 0
            },
            "expected_by_section": expected,
            "actual_by_section": actual,
            "courses_created": created
        },
        "conflicts": [
            {
                'type': c['type'],
                'message': c['message'],
                'details': {k: v for k, v in c.items() if k not in ['type', 'message']}
            }
            for c in final_conflicts
        ]
    }

    return output


def generate_schedule_from_data(json_data):
    """
    Main entry point called by Flask server
    Takes JSON data and returns schedule result
    """
    global title, firstbreak, secondbreak, teacher_load, teacher_availability
    global courses, rooms_list, sections_list, days, time_slots, time_map
    
    try:
        title = json_data["Title"]
        firstbreak = float(json_data["firstBreakTime"])
        secondbreak = float(json_data["secondBreakTime"])
        teachers_dict = json_data["TeacherLoad"]
        teacher_availability_dict = json_data["TeacherAvailability"]
        rooms = json_data["RoomInfo"]
        subjects = json_data["Subject"]
        sections = json_data["Section"]

        normalized_teacher_availability = {}
        for tid, tdata in teacher_availability_dict.items():
            normalized_avail = {}
            for day_key, hours in tdata.get('availability', {}).items():
                normalized_day = DAY_MAPPING.get(day_key.upper(), day_key)
                normalized_avail[normalized_day] = hours
            
            normalized_teacher_availability[tid] = {
                'name': tdata.get('name', tid),
                'status': tdata.get('status', 'FULL-TIME'),
                'availability': normalized_avail
            }
        
        teacher_availability_dict = normalized_teacher_availability

        teacher_load = []
        for tid, tdata in teachers_dict.items():
            teacher_load.append({
                'teacher_id': tid,
                'teacher_name': tdata['name'],
                'courses': tdata['courses'],
                'max_units': float(tdata['maxUnits'])
            })
        
        teacher_availability = []
        for tid, tdata in teacher_availability_dict.items():
            teacher_availability.append({
                'teacher_id': tid,
                'teacher_name': tdata['name'],
                'status': tdata['status'],
                **{day: tdata['availability'][day] for day in tdata['availability']}
            })
        
        courses = []
        for subj in subjects:
            courses.append({
                'code': subj['courseCode'],
                'name': subj['courseTitle'],
                'type': subj['subjectType'],
                'units': float(subj['units']),
                'days': int(subj['daysPerWeek'])
            })
        
        rooms_list = []
        for room in rooms:
            rooms_list.append({
                'room': room['roomName'],
                'type': room['roomType'],
                'capacity': int(room.get('roomCapacity', 40))
            })
        
        sections_list = []
        for sec in sections:
            sections_list.append({
                'name': sec['sectionName'],
                'courses': sec['courseCodes'],
                'student_count': int(sec.get('sectionStudents', 30))
            })

        days = []
        for teacher_data in teacher_availability:
            for day in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']:
                if day in teacher_data and teacher_data[day] and day not in days:
                    days.append(day)
        
        if not days:
            days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
        
        time_slots = TIME_SLOTS
        time_map = TIME_MAP

        print("Starting schedule generation...")
        sys.stdout.flush()
        
        best_schedule, best_fitness, all_generation_bests = run_genetic_algorithm()
        
        if not best_schedule:
            return {
                "error": "Failed to generate any valid schedules",
                "title": title,
                "generated_schedule": [],
                "statistics": {"completion_rate": 0}
            }
        
        print("Schedule generation complete!")
        sys.stdout.flush()
        
        return prepare_output(best_schedule, best_fitness, all_generation_bests)
        
    except Exception as e:
        print(f"Error in schedule generation: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "error": str(e),
            "title": json_data.get("Title", "Unknown"),
            "generated_schedule": [],
            "statistics": {"completion_rate": 0}
        }
    
    
