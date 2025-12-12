"""
timetable_csp.py
Reads data from CSV files, handles hard constraints:
- Instructor qualification (InstructorCourses.csv + optional Instructor.csv)
- Room compatibility & capacity (Rooms.csv)
- Timeslot availability & slot type (TimeSlots.csv)
- Student clashes per section (Sections.csv)
- Session types from LectureMapping.csv (Lecture, Lab, Short/Long Tutorial)

Outputs:
- timetable_solution.csv
- timetable_failures.csv
"""

import os
import pandas as pd
from collections import defaultdict

# -------------------------
# Config
# -------------------------
ALLOW_FALLBACK = True        # if a course has no qualified instructors, allow any instructor
MIN_LECTURE_DURATION = 80    # minutes threshold for "long" (lecture/tut)
MAX_TUTORIAL_DURATION = 79   # minutes threshold for "short" tutorial
ROOM_CAPACITY_RELAX = 0.0    # allow rooms below capacity by this fraction (0.0 = strict)

# -------------------------
# Helpers
# -------------------------
def safe_str(x):
    return "" if (pd.isna(x) or x is None) else str(x).strip()

def int_safe(x, default=0):
    try:
        return int(float(x))
    except Exception:
        return default

def mins_to_hhmm(m):
    try:
        m = int(m)
    except Exception:
        return "N/A"
    h = m // 60
    mm = m % 60
    return f"{h:02d}:{mm:02d}"

def find_col(df, candidates):
    if df is None or df.empty:
        return None
    cols = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in cols:
            return cols[cand.lower()]
    return None

def compatible_room_by_session(session_type, room_type):
    """
    Session type to room type:
    - Lab → Lab or PhysicsLab; allow Classroom/Hall/Theater as fallback
    - Lecture/Tutorial → Classroom/Hall/Theater; allow Lab as fallback
    """
    st = (session_type or "").lower()
    rt = (room_type or "").lower()

    is_lab_session = ("lab" in st)
    is_tutorial = ("tutorial" in st)
    is_lecture = ("lecture" in st)

    if is_lab_session:
        if "lab" in rt or "physics" in rt:
            return True
        if "classroom" in rt or "hall" in rt or "theater" in rt:
            return True
        return False

    if is_lecture or is_tutorial:
        if "classroom" in rt or "hall" in rt or "theater" in rt:
            return True
        if "lab" in rt or "physics" in rt:
            return True
        return False

    # Fallback
    return ("classroom" in rt or "hall" in rt or "theater" in rt or "lab" in rt or "physics" in rt)

def slottype_matches_session(slot_type, slot_duration, session_type):
    """
    Tutorial slot type enforcement:
    - Short Tutorial → slot_type 'short' or duration <= MAX_TUTORIAL_DURATION
    - Long Tutorial → slot_type 'long' or duration >= MIN_LECTURE_DURATION
    - Lecture/Lab → any slot allowed
    """
    st = (session_type or "").lower()
    sl = (slot_type or "").lower()

    if "short tutorial" in st or ("short" in st and "tutorial" in st):
        if sl and "short" in sl:
            return True
        return slot_duration <= MAX_TUTORIAL_DURATION
    if "long tutorial" in st or ("long" in st and "tutorial" in st):
        if sl and "long" in sl:
            return True
        return slot_duration >= MIN_LECTURE_DURATION

    return True

# -------------------------
# Load CSV files
# -------------------------
def load_tables_csv(base_path="."):
    """
    Returns: instructors_df, instr_courses_df, courses_df, rooms_df, timeslots_df, sections_df, lecturemap_df
    """
    try:
        path = os.path.abspath(base_path)
        # Instructor.csv is optional; if missing, create empty
        instr_path = os.path.join(path, "Instructor.csv")
        instructors_df = pd.read_csv(instr_path) if os.path.exists(instr_path) else pd.DataFrame(columns=["InstructorID", "Name", "Role"])

        instr_courses_df = pd.read_csv(os.path.join(path, "InstructorCourses.csv"))
        courses_df = pd.read_csv(os.path.join(path, "Courses.csv"))
        rooms_df = pd.read_csv(os.path.join(path, "Rooms.csv"))
        timeslots_df = pd.read_csv(os.path.join(path, "TimeSlots.csv"))
        sections_df = pd.read_csv(os.path.join(path, "Sections.csv"))
        lecturemap_df = pd.read_csv(os.path.join(path, "LectureMapping.csv"))
    except Exception as e:
        print(f"⚠️ Could not read CSV files: {e}")
        empty_df = pd.DataFrame()
        return empty_df, empty_df, empty_df, empty_df, empty_df, empty_df, empty_df

    print("✅ Loaded all CSV files successfully.")
    return instructors_df, instr_courses_df, courses_df, rooms_df, timeslots_df, sections_df, lecturemap_df

# -------------------------
# Preprocess
# -------------------------
def preprocess(instructors_df, instr_courses_df, courses_df, rooms_df, timeslots_df, sections_df, lecturemap_df):
    # Courses
    courses = {}
    for _, r in courses_df.iterrows():
        cid = safe_str(r.get("CourseID"))
        if not cid:
            continue
        courses[cid] = {
            "name": safe_str(r.get("CourseName")),
            "type": safe_str(r.get("Type")).lower(),
            "has_lecture": int_safe(r.get("HasLecture", 0)) == 1,
            "has_lab": int_safe(r.get("HasLab", 0)) == 1,
            "has_long_tut": int_safe(r.get("HasLongTut", 0)) == 1,
            "has_short_tut": int_safe(r.get("HasShortTut", 0)) == 1
        }

    # Instructors (names/roles optional)
    instructors = defaultdict(lambda: {"name": "", "quals": set(), "role": "professor"})
    role_col = find_col(instructors_df, ["Role", "Type", "Rank"])
    name_col = find_col(instructors_df, ["Name", "InstructorName", "FullName"])
    id_col = find_col(instructors_df, ["InstructorID", "ID"])

    for _, r in instructors_df.iterrows():
        iid = safe_str(r.get(id_col)) if id_col else safe_str(r.get("InstructorID"))
        if not iid:
            continue
        instructors[iid]["name"] = safe_str(r.get(name_col)) if name_col else iid
        if role_col:
            role_val = safe_str(r.get(role_col)).lower()
            instructors[iid]["role"] = role_val if role_val else "professor"

    # Qualifications
    for _, r in instr_courses_df.iterrows():
        iid = safe_str(r.get("InstructorID"))
        cid = safe_str(r.get("CourseID"))
        if iid and cid:
            instructors[iid]["quals"].add(cid)
        # Ensure presence even if Instructor.csv missing
        if iid not in instructors:
            instructors[iid]["name"] = iid
            instructors[iid]["role"] = "professor"

    # Rooms
    room_id_col = find_col(rooms_df, ["RoomID", "ID"])
    room_type_col = find_col(rooms_df, ["RoomType", "Type"])
    cap_col = find_col(rooms_df, ["Capacity", "Cap", "RoomCapacity"])
    rooms = {}
    for _, r in rooms_df.iterrows():
        rid = safe_str(r.get(room_id_col)) if room_id_col else safe_str(r.get("RoomID"))
        if not rid:
            continue
        rtype = safe_str(r.get(room_type_col)).lower() if room_type_col else safe_str(r.get("RoomType")).lower()
        rcap = int_safe(r.get(cap_col, 0))
        rooms[rid] = {"type": rtype, "capacity": rcap}

    # Timeslots
    tid_col = find_col(timeslots_df, ["TimeSlotID", "SlotID", "ID"])
    day_col = find_col(timeslots_df, ["Day", "Weekday"])
    start_col = find_col(timeslots_df, ["StartMin", "StartMinute", "Start"])
    end_col = find_col(timeslots_df, ["EndMin", "EndMinute", "End"])
    stype_col = find_col(timeslots_df, ["SlotType", "Type"])

    timeslots = []
    timeslot_info = {}
    for _, r in timeslots_df.iterrows():
        tid = safe_str(r.get(tid_col)) if tid_col else safe_str(r.get("TimeSlotID"))
        if not tid:
            continue
        timeslots.append(tid)
        start = int_safe(r.get(start_col), 0)
        end = int_safe(r.get(end_col), 0)
        duration = int_safe(r.get("Duration")) if "Duration" in timeslots_df.columns else max(0, end - start)
        if duration == 0 and start and end:
            duration = max(0, end - start)
        timeslot_info[tid] = {
            "day": safe_str(r.get(day_col)),
            "start_min": start,
            "end_min": end if end else start + duration,
            "duration": duration,
            "slot_type": safe_str(r.get(stype_col)).lower() if stype_col else ""
        }

    # Timeslot overlap map (same day and overlapping minutes)
    overlap_map = {tid: set() for tid in timeslots}
    for i, a in enumerate(timeslots):
        ai = timeslot_info[a]
        for b in timeslots[i + 1:]:
            bi = timeslot_info[b]
            if ai["day"] and bi["day"] and ai["day"].lower() == bi["day"].lower():
                if (ai["start_min"] < bi["end_min"]) and (bi["start_min"] < ai["end_min"]):
                    overlap_map[a].add(b)
                    overlap_map[b].add(a)

    # Sections
    section_students = {}
    section_courses = {}
    sec_id_col = find_col(sections_df, ["SectionID", "ID"])
    student_col = find_col(sections_df, ["StudentCount", "Students", "Enrolled"])
    courses_col = find_col(sections_df, ["Courses", "CourseList"])
    for _, r in sections_df.iterrows():
        sid = safe_str(r.get(sec_id_col)) if sec_id_col else safe_str(r.get("SectionID"))
        if not sid:
            continue
        section_students[sid] = int_safe(r.get(student_col), 0)
        courses_str = safe_str(r.get(courses_col)) if courses_col else safe_str(r.get("Courses"))
        section_courses[sid] = [c.strip() for c in courses_str.split(",") if c.strip()]

    # Lecture mapping → sessions
    sessions = []
    sm_sec_col = find_col(lecturemap_df, ["SectionID", "Section"])
    sm_course_col = find_col(lecturemap_df, ["CourseID", "Course"])
    sm_type_col = find_col(lecturemap_df, ["SessionType", "Type"])

    lecturemap_df = lecturemap_df.dropna(subset=[sm_sec_col, sm_course_col, sm_type_col])
    for _, r in lecturemap_df.iterrows():
        sid = safe_str(r.get(sm_sec_col))
        cid = safe_str(r.get(sm_course_col))
        stype = safe_str(r.get(sm_type_col))
        if not sid or not cid or not stype:
            continue
        students = section_students.get(sid, 0)
        sessions.append({
            "section": sid,
            "course": cid,
            "session_type": stype,
            "students": students
        })

    print(f"✅ Prepared {len(sessions)} session entries from LectureMapping.")
    return courses, instructors, rooms, timeslots, timeslot_info, overlap_map, sessions

# -------------------------
# Variable
# -------------------------
class LectureVar:
    def __init__(self, course, section, session_type, students):
        self.course = course
        self.section = section
        self.session_type = session_type
        self.students = students
        self.name = f"{course}_{section}_{session_type}"

    def __repr__(self):
        return self.name

# -------------------------
# Build variables & domains
# -------------------------
def build_vars_domains(courses, instructors, rooms, timeslots, timeslot_info, overlap_map, sessions):
    variables, domains = [], {}
    all_instructors = list(instructors.keys())

    for s in sessions:
        cid = s["course"]
        sid = s["section"]
        stype = s["session_type"]
        students = int_safe(s["students"], 0)

        if students <= 0:
            print(f"⚠️ Skipping {cid}/{sid}/{stype} because students={students}. Check Sections.csv")
            continue
        if cid not in courses:
            print(f"⚠️ Warning: Course {cid} listed in LectureMapping not found in Courses.csv. Skipping.")
            continue

        v = LectureVar(cid, sid, stype, students)
        variables.append(v)

        dom = []
        qualified_instrs = [iid for iid, info in instructors.items() if cid in info["quals"]]
        if not qualified_instrs and ALLOW_FALLBACK:
            qualified_instrs = all_instructors[:]

        prefer_assistant = ("lab" in stype.lower() or "tutorial" in stype.lower())

        for t in timeslots:
            ts = timeslot_info.get(t, {})
            if not ts:
                continue
            slot_duration = ts.get("duration", 0)
            if not slottype_matches_session(ts.get("slot_type", ""), slot_duration, stype):
                continue

            for r_id, r_info in rooms.items():
                if not compatible_room_by_session(stype, r_info["type"]):
                    continue

                min_capacity = students
                if ROOM_CAPACITY_RELAX > 0:
                    min_capacity = int(round(students * (1 - ROOM_CAPACITY_RELAX)))
                if r_info["capacity"] < min_capacity:
                    continue

                for instr_id in qualified_instrs:
                    instr_role = instructors.get(instr_id, {}).get("role", "professor")
                    pref_flag = bool(prefer_assistant and ("assistant" in instr_role or "ta" in instr_role or "lab" in instr_role))
                    dom.append((t, r_id, instr_id, cid in instructors.get(instr_id, {}).get("quals", set()), pref_flag))

        domains[v] = dom

        if not dom:
            print(f"\n⚠️ WARNING: empty domain for {v.name}")
            print("  CourseID:", cid)
            print("  Students:", students)
            print("  Qualified instructors (count):", len([i for i in instructors if cid in instructors.get(i, {}).get("quals", set())]))
            print("  Rooms (count):", len(rooms))
            large_rooms = [r for r in rooms if rooms[r]["capacity"] >= students]
            print("  Rooms with capacity >= students (count):", len(large_rooms), "sample:", large_rooms[:8])
            print("  TimeSlots (count):", len(timeslots))
            sample_slots = [(t, timeslot_info[t]["duration"], timeslot_info[t]["slot_type"]) for t in list(timeslots)[:6]]
            print("  Timeslots (sample):", sample_slots)
            print("  Tip: Check Rooms.csv capacities/RoomType; InstructorCourses.csv qualifications; Sections.csv student counts; TimeSlots durations.\n")

    print(f"✅ Built {len(variables)} variables with domains.")
    return variables, domains

# -------------------------
# Solver (greedy backtracking with overlap checks)
# -------------------------
def solve_timetable(variables, domains, timeslot_info, overlap_map, rooms):
    assigned = {}
    failed_assignments = []

    used_room_ts = defaultdict(set)     # room_id -> set(timeslot IDs)
    used_instr_ts = defaultdict(set)    # instr_id -> set(timeslot IDs)
    used_section_ts = defaultdict(set)  # section_id -> set(timeslot IDs)

    sorted_vars = sorted(variables, key=lambda v: (-v.students, len(domains.get(v, []))))

    for v in sorted_vars:
        dom = domains.get(v, [])
        if not dom:
            print(f"🔴 FAILED: {v.name} (Students: {v.students}) - NO DOMAIN")
            failed_assignments.append(v)
            continue

        def room_capacity_diff(option):
            _, room_id, _, _, _ = option
            return abs(rooms.get(room_id, {}).get("capacity", 9999) - v.students)

        sorted_domain = sorted(dom, key=lambda x: (not x[4], room_capacity_diff(x)))

        assigned_slot = False
        for option in sorted_domain:
            t, r, instr, _, _ = option

            # Check conflicts using overlap map
            conflict = False
            for used_t in used_room_ts[r]:
                if t == used_t or t in overlap_map.get(used_t, set()):
                    conflict = True
                    break
            if conflict:
                continue

            for used_t in used_instr_ts[instr]:
                if t == used_t or t in overlap_map.get(used_t, set()):
                    conflict = True
                    break
            if conflict:
                continue

            for used_t in used_section_ts[v.section]:
                if t == used_t or t in overlap_map.get(used_t, set()):
                    conflict = True
                    break
            if conflict:
                continue

            # Assign
            assigned[v] = option
            used_room_ts[r].add(t)
            used_instr_ts[instr].add(t)
            used_section_ts[v.section].add(t)
            assigned_slot = True
            break

        if not assigned_slot:
            failed_assignments.append(v)
            print(f"🔴 FAILED: {v.name} (Students: {v.students}) - All slots clashed")

    return assigned, failed_assignments

# -------------------------
# Export CSV
# -------------------------
def export_results(assigned, failed, timeslot_info_local, instructors_map, out_path="."):
    rows = []
    for v, val in assigned.items():
        if not val:
            continue
        t, r, instr_id, qual, pref = val
        info = timeslot_info_local.get(t, {"day": "N/A", "start_min": "N/A", "end_min": "N/A", "slot_type": "N/A"})
        instr_name = instructors_map.get(instr_id, {}).get("name", instr_id)
        rows.append({
            "Course": v.course,
            "Section": v.section,
            "SessionType": v.session_type,
            "Students": v.students,
            "Day": info["day"],
            "StartMin": info["start_min"],
            "EndMin": info["end_min"],
            "StartHHMM": mins_to_hhmm(info["start_min"]),
            "EndHHMM": mins_to_hhmm(info["end_min"]),
            "SlotType": info["slot_type"],
            "Room": r,
            "Instructor": instr_name,
            "InstructorQualified": bool(qual),
            "TimeslotIsPreferred": bool(pref)
        })

    solution_file = os.path.join(out_path, "timetable_solution.csv")
    pd.DataFrame(rows).to_csv(solution_file, index=False)
    print(f"✅ Exported {len(rows)} successful assignments to {solution_file}")

    if failed:
        failed_rows = [{
            "Course": v.course,
            "Section": v.section,
            "SessionType": v.session_type,
            "Students": v.students
        } for v in failed]
        failures_file = os.path.join(out_path, "timetable_failures.csv")
        pd.DataFrame(failed_rows).to_csv(failures_file, index=False)
        print(f"⚠️ Exported {len(failed_rows)} failed assignments to {failures_file}")

# -------------------------
# Main
# -------------------------
def main(base_path="."):
    print("📘 Loading data from CSV files ...")
    data = load_tables_csv(base_path)
    if data[0].empty and data[1].empty:
        print("❌ Data loading failed. Exiting.")
        return

    print("⚙️ Preprocessing data ...")
    courses, instructors, rooms, timeslots, t_info, overlap_map, sessions = preprocess(*data)
    print(f"📊 Data ready: {len(courses)} courses, {len(instructors)} instructors, {len(rooms)} rooms, {len(timeslots)} timeslots, {len(sessions)} sessions.")

    print("🧩 Building variables and domains ...")
    variables, domains = build_vars_domains(courses, instructors, rooms, timeslots, t_info, overlap_map, sessions)

    if not variables:
        print("❌ No variables were created. Check your LectureMapping and Sections data.")
        print("🎉 Done.")
        return

    print("🧠 Solving timetable... please wait.")
    assigned, failed = solve_timetable(variables, domains, t_info, overlap_map, rooms)

    print("📄 Exporting results...")
    export_results(assigned, failed, t_info, instructors, base_path)

    print("🎉 Done.")

if __name__ == "__main__":
    main()
