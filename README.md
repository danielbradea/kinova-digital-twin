# Kinova Digital Twin (KDT)

A Python desktop application for monitoring a six-joint Kinova Gen3 arm, recording feedback in PostgreSQL, replaying recorded motion and exploring telemetry charts. The interface uses PySide6, PyVista/VTK for the robot model and PyQtGraph for charts.

## Installation

The application has been tested on Windows with **64-bit Python 3.14**. A desktop session and graphics drivers supporting OpenGL are required for the 3D viewer.

Open PowerShell in the project directory and run:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Virtual environment activation is optional because these commands explicitly use its Python executable. Installation requires internet access to PyPI and the official Kinova package server. `requirements.txt` pins the runtime packages to the versions used in the tested environment; pip also installs their dependencies. It includes the official Kortex SDK wheel and Psycopg's binary distribution, so a local PostgreSQL client compiler is unnecessary.

**PostgreSQL is a separate service:** pip installs its Python driver, not the database server. Install/start PostgreSQL before recording or browsing database records. Live Reading and Live Charts require a robot connection but do not require a database connection.

## Database setup

Create a database and login role using PostgreSQL administration tools. Then connect to that database as the intended application user and run `database/schema.sql`. For example:

```powershell
psql -h localhost -p 5432 -U kinova -d kinova -f database/schema.sql
```

The SQL file creates `kinova_feedback` and a timestamp index. It does not create a login or database, and it does not alter an existing table. An existing table must contain the same columns. The recorder needs INSERT permission; the table and digital twin pages need SELECT permission.

Open **Data Recorder** and enter the database host, port, database name, username and password. Set the recording table to `kinova_feedback`, or use `schema.table` for another compatible table. The values initially shown in the connection form are development defaults; change them to match your installation. Settings are shared between pages for the current application session and are not persisted across restarts.

Each record contains 41 fields:

| Fields | Meaning / units |
| --- | --- |
| `time` | UTC acquisition timestamp (`TIMESTAMPTZ`) |
| `joint_1_*` through `joint_6_*` | Position (degrees), velocity (degrees/s), torque (N·m), motor current (A), motor temperature (°C) |
| `arm_voltage`, `arm_current` | Supply voltage (V) and current (A) |
| `temperature_cpu`, `temperature_ambient` | CPU and ambient temperatures (°C) |
| `tool_x`, `tool_y`, `tool_z` | Tool position (m) |
| `tool_theta_x`, `tool_theta_y`, `tool_theta_z` | Tool orientation (degrees) |

Table filters and displayed table timestamps use `Europe/Bucharest`. Database queries convert filter bounds to UTC; digital twin telemetry and chart axes display UTC. The ending filter second is included in searches.

## Pages

Use the menu button in the header to open the sidebar.

### Home

Introduces the application and displays the Kinova 3D model. Rotate and zoom the viewer to inspect the arm.

### Data Recorder

Configures robot credentials/IP/UDP port and PostgreSQL credentials. **Test Connections** checks the database and authenticates with the robot, reading feedback. Both tests must succeed before recording starts.

Choose a sampling interval (10–10,000 ms; default 100 ms) and destination table. **Start Recording** acquires feedback in a background worker and saves batches of 100 samples. **Stop** flushes the remaining samples and closes the connections. Closing the window while recording asks whether to stop recording and close or cancel. Cancel keeps recording active; confirming waits for the remaining samples to be saved and the worker to finish before closing. The sample counter shows committed records. Connection settings are disabled during recording. The table must already exist.

### Live Reading

Uses the robot connection configured in Data Recorder. **Start stream** reads feedback approximately every 100 ms and updates the 3D model, six joint position cards and full joint/base/tool telemetry. **Stop stream** retains the last displayed pose. **Recenter camera** restores the camera framing. Leaving this page stops its stream. On smaller windows, the information panels are organized into tabs.

### Data Table

Loads the latest 100 database records on first entry. Use the start/end date and time filters with **Search** to query a period. **Latest 100** loads the newest records; **Reset** restores today's full-day filters and reloads the latest records. Searches display at most 10,000 records and report when the result is truncated.

Select records using the checkbox column. Click its header to select or clear all loaded records. **Show in Kinova** opens the selected poses in the digital twin. **Show charts** opens the selected telemetry in the selected-data charts page. These actions become available when at least one row is checked. Numeric cells show rounded values; tooltips expose the original values.

**Export CSV** saves only the checked rows, in their table order, to a file of your choice. The export includes all 41 database columns with their original names and full numeric precision, UTC ISO 8601 timestamps and empty cells for missing values. Files use comma separators and UTF-8 with a BOM for Excel compatibility. Exporting preserves the current selection.

### Kinova Digital Twin

Entering through the sidebar loads the latest database pose. **Latest position** reloads it; **Recenter camera** restores the view. Joint cards and the details panel display the current record.

After using **Show in Kinova** in Data Table, selected records are sorted chronologically. Use **Play**, **Pause**, **Stop**, the timeline slider, **Loop** and the speed selector (0.25×–4×) to replay them. Playback follows the stored timestamp intervals and animates only the displayed model. **Skip recording gaps** is enabled by default: gaps longer than both one second and ten typical sample intervals are shortened to one typical interval. Disable it to retain the original pauses between recording sessions. Leaving the page pauses playback.

### Live Charts

Uses the same robot settings as Live Reading. **Start stream** collects feedback; **Stop stream** retains the charts; **Clear history** resets the history. Leaving this page stops its stream.

Choose a visible interval of 30, 60 or 120 seconds. History is limited to 120 seconds / 2,400 samples. The joint chart supports position, velocity, torque, current and temperature, with individual joint visibility switches and a mouse hover readout. Additional charts show estimated electrical power (`P = U × I`), CPU/ambient temperature, tool XYZ position and a trajectory projected onto XY, XZ or YZ.

Joint position charts unwrap angles across the 0°/360° boundary. Gaps longer than one second interrupt plotted lines. Use the graph's mouse controls to zoom and pan; active updates refresh the visible time range.

### Selected Data Charts

Opened with **Show charts** in Data Table. Displays the same chart types as Live Charts for the complete selection in chronological order, including repeated timestamps. This page does not connect to the robot and does not apply the live history limits. **Back to data** returns to the table with its selection retained.

## Typical workflow

1. Configure robot and database connections in Data Recorder and test both.
2. Start recording, then stop when the desired movement has been captured.
3. Open Data Table and load/filter the recorded period.
4. Check records and select **Show in Kinova** for replay or **Show charts** for analysis.

Live Reading and Live Charts can also be used independently for monitoring. These pages read feedback; they do not issue motion commands to the robot.

## Project structure

```text
main.py                         Application entry point and Windows icon
appLayout.py                    Navigation, shared configuration and shutdown
requirements.txt                Python runtime dependencies
database/schema.sql             PostgreSQL feedback table and time index
view/kinova3DWidget.py           URDF loading and 3D rendering
view/home_page/                 Home page
view/data_recorder_page/        Connection forms and recording worker
view/live_reading_page/         Live telemetry and acquisition worker
view/data_table_page/           Table model, filters and database query worker
view/kinova_view_page/          Latest database pose and recorded playback
view/charts_view_page/          Live/selected charts and telemetry history
resources/icons/                PNG and Windows ICO application icons
resources/kortex_description/   Gen3 6-DOF URDF, required STL meshes and attribution
```

Keep `resources` alongside `main.py` when copying the project. Resource paths are resolved relative to the source files. The retained model is `GEN3-6DOF_NO-VISION_URDF_ARM_V01.urdf`; see the retained model README for upstream attribution.
