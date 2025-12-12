// List of required CSV files for the solver
const requiredFiles = [
    "InstructorCourses.csv", "Courses.csv", "Rooms.csv", 
    "TimeSlots.csv", "Sections.csv", "LectureMapping.csv", 
    "Instructor.csv" // Optional, but useful to include
];

let dataTable;

/**
 * LOGGING FUNCTIONS (Mimicking GuiLogger)
 */
function log(message, tag = 'info') {
    const logOutput = document.getElementById('log-output');
    const line = document.createElement('div');
    line.className = `log-line ${tag}`;
    line.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
    logOutput.appendChild(line);
    // Scroll to bottom
    logOutput.scrollTop = logOutput.scrollHeight;
}

function clearLog() {
    document.getElementById('log-output').innerHTML = '';
    log('Log cleared.', 'debug');
}

function setStatus(text, tag = 'idle') {
    const statusEl = document.getElementById('status-display');
    statusEl.textContent = `(${text})`;
    statusEl.className = `status-${tag}`;
}

/**
 * INITIALIZATION
 */
document.addEventListener('DOMContentLoaded', () => {
    // 1. Generate file upload inputs
    const inputGrid = document.getElementById('file-inputs');
    requiredFiles.forEach(fileName => {
        const div = document.createElement('div');
        div.innerHTML = `
            <label for="${fileName}">${fileName}:</label>
            <input type="file" id="${fileName}" name="${fileName}" accept=".csv" required>
        `;
        inputGrid.appendChild(div);
    });

    // 2. Initialize DataTable (must be done before populating)
    initializeDataTable([]);

    log('Interface loaded. Ready to receive files.', 'ok');
});

function initializeDataTable(data) {
    // Destroy previous instance if it exists
    if (dataTable) {
        dataTable.destroy();
        $('#results-table').empty(); // Clear table structure
    }

    if (data.length === 0) {
        // Initialize with default columns if no data is available yet
        const defaultHeaders = [
            { title: "Course" }, { title: "Section" }, { title: "Session Type" },
            { title: "Students" }, { title: "Day" }, { title: "Start Time" },
            { title: "Room" }, { title: "Instructor" }, { title: "Qualified?" }
        ];
        
        dataTable = $('#results-table').DataTable({
            columns: defaultHeaders,
            data: [],
            paging: true,
            searching: true,
            info: true
        });
        return;
    }

    // Get column definitions from the first row object keys
    const columns = Object.keys(data[0]).map(key => ({
        title: key,
        data: key
    }));

    dataTable = $('#results-table').DataTable({
        columns: columns,
        data: data,
        paging: true,
        searching: true, // Enables the built-in search/filter
        info: true,
        scrollX: true, // Scrollable horizontally
        order: [[4, 'asc'], [5, 'asc']], // Default sort by Day and Start Time

        // Custom row coloring based on logic from Python solver
        rowCallback: function(row, data) {
            $(row).removeClass('dt-row-big dt-row-warn dt-row-ok');
            
            const students = parseInt(data.Students) || 0;
            const qualified = data.InstructorQualified === 'False' || data.InstructorQualified === false;

            if (students >= 200) {
                $(row).addClass('dt-row-big');
            } else if (qualified) {
                $(row).addClass('dt-row-warn');
            } else {
                $(row).addClass('dt-row-ok');
            }
        }
    });
}


/**
 * SIMULATED SOLVER EXECUTION (Replace with AJAX in a real implementation)
 */
async function simulateSolverRun() {
    clearLog();
    setStatus('Running...', 'running');
    
    // In a real application, you would collect the File objects here:
    // const files = requiredFiles.map(id => document.getElementById(id).files[0]);
    // Then use a FormData object and an AJAX request (fetch or jQuery.ajax)
    // to send them to a server endpoint running Python/Flask/Django.
    
    log('INFO: Starting file upload and preprocessing...', 'info');
    await new Promise(r => setTimeout(r, 1000)); // Simulate file transfer delay

    log('INFO: Solver instance initialized on server.', 'info');
    await new Promise(r => setTimeout(r, 1500)); // Simulate solver startup

    log('INFO: Searching for a valid solution (1/3).', 'info');
    await new Promise(r => setTimeout(r, 2000));
    log('INFO: Solving hard constraints (2/3).', 'info');
    await new Promise(r => setTimeout(r, 2000));
    log('INFO: Optimizing room utilization (3/3).', 'info');
    
    // Simulate the server sending back the CSV data (converted to JSON)
    const simulatedData = getSimulatedTimetableData();

    await new Promise(r => setTimeout(r, 1500)); 
    
    // --- Display Results ---
    if (simulatedData.length > 0) {
        log(`✅ Exported ${simulatedData.length} successful assignments.`, 'ok');
        initializeDataTable(simulatedData);
        setStatus('Done', 'done');
    } else {
        log('ERROR: Solver failed to produce any assignments. Check input files.', 'error');
        setStatus('Error', 'error');
    }
}


/**
 * DUMMY DATA FOR DEMO
 */
function getSimulatedTimetableData() {
    // This structured data mimics the output of your Python solver's final dataframe.
    return [
        {
            "Course": "CS101", "Section": "A", "SessionType": "Lecture", "Students": 180, 
            "Day": "Mon", "StartMin": 540, "EndMin": 620, "StartHHMM": "09:00", 
            "EndHHMM": "10:20", "Room": "Hall A", "Instructor": "Dr. Smith", 
            "InstructorQualified": true, "TimeslotIsPreferred": false
        },
        {
            "Course": "MA205", "Section": "B", "SessionType": "Lab", "Students": 50, 
            "Day": "Mon", "StartMin": 630, "EndMin": 710, "StartHHMM": "10:30", 
            "EndHHMM": "11:50", "Room": "Comp Lab 2", "Instructor": "Ms. Williams", 
            "InstructorQualified": true, "TimeslotIsPreferred": true
        },
        {
            "Course": "PH310", "Section": "A", "SessionType": "Lecture", "Students": 250, 
            "Day": "Tue", "StartMin": 540, "EndMin": 620, "StartHHMM": "09:00", 
            "EndHHMM": "10:20", "Room": "Hall A", "Instructor": "Prof. Jones", 
            "InstructorQualified": false, "TimeslotIsPreferred": false // Will be tagged as WARNING
        },
        {
            "Course": "CS102", "Section": "C", "SessionType": "Long Tutorial", "Students": 45, 
            "Day": "Tue", "StartMin": 720, "EndMin": 800, "StartHHMM": "12:00", 
            "EndHHMM": "13:20", "Room": "L-101", "Instructor": "Dr. Smith", 
            "InstructorQualified": true, "TimeslotIsPreferred": true
        },
        {
            "Course": "ME401", "Section": "D", "SessionType": "Lab", "Students": 30, 
            "Day": "Wed", "StartMin": 540, "EndMin": 620, "StartHHMM": "09:00", 
            "EndHHMM": "10:20", "Room": "Physics Lab", "Instructor": "Dr. Patel", 
            "InstructorQualified": true, "TimeslotIsPreferred": true
        },
        {
            "Course": "EC305", "Section": "E", "SessionType": "Short Tutorial", "Students": 15, 
            "Day": "Fri", "StartMin": 480, "EndMin": 530, "StartHHMM": "08:00", 
            "EndHHMM": "08:50", "Room": "Classroom 5", "Instructor": "Ms. Williams", 
            "InstructorQualified": true, "TimeslotIsPreferred": true
        }
    ];
}