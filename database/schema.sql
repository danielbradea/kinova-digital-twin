-- Create the feedback table in the database configured in Data Recorder.
-- Run as the application user or grant INSERT and SELECT afterwards.
CREATE TABLE IF NOT EXISTS kinova_feedback (
    time TIMESTAMPTZ NOT NULL,
    joint_1_position DOUBLE PRECISION,
    joint_1_velocity DOUBLE PRECISION,
    joint_1_torque DOUBLE PRECISION,
    joint_1_current DOUBLE PRECISION,
    joint_1_temperature DOUBLE PRECISION,
    joint_2_position DOUBLE PRECISION,
    joint_2_velocity DOUBLE PRECISION,
    joint_2_torque DOUBLE PRECISION,
    joint_2_current DOUBLE PRECISION,
    joint_2_temperature DOUBLE PRECISION,
    joint_3_position DOUBLE PRECISION,
    joint_3_velocity DOUBLE PRECISION,
    joint_3_torque DOUBLE PRECISION,
    joint_3_current DOUBLE PRECISION,
    joint_3_temperature DOUBLE PRECISION,
    joint_4_position DOUBLE PRECISION,
    joint_4_velocity DOUBLE PRECISION,
    joint_4_torque DOUBLE PRECISION,
    joint_4_current DOUBLE PRECISION,
    joint_4_temperature DOUBLE PRECISION,
    joint_5_position DOUBLE PRECISION,
    joint_5_velocity DOUBLE PRECISION,
    joint_5_torque DOUBLE PRECISION,
    joint_5_current DOUBLE PRECISION,
    joint_5_temperature DOUBLE PRECISION,
    joint_6_position DOUBLE PRECISION,
    joint_6_velocity DOUBLE PRECISION,
    joint_6_torque DOUBLE PRECISION,
    joint_6_current DOUBLE PRECISION,
    joint_6_temperature DOUBLE PRECISION,
    arm_voltage DOUBLE PRECISION,
    arm_current DOUBLE PRECISION,
    temperature_cpu DOUBLE PRECISION,
    temperature_ambient DOUBLE PRECISION,
    tool_x DOUBLE PRECISION,
    tool_y DOUBLE PRECISION,
    tool_z DOUBLE PRECISION,
    tool_theta_x DOUBLE PRECISION,
    tool_theta_y DOUBLE PRECISION,
    tool_theta_z DOUBLE PRECISION
);

-- Support latest-record and time-range queries.
CREATE INDEX IF NOT EXISTS kinova_feedback_time_idx
    ON kinova_feedback (time DESC);
