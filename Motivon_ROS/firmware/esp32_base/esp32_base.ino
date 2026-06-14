#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <esp_arduino_version.h>

#include <micro_ros_arduino.h>

#include <geometry_msgs/msg/twist.h>
#include <rcl/rcl.h>
#include <rclc/executor.h>
#include <rclc/rclc.h>
#include <rmw_microros/rmw_microros.h>
#include <rosidl_runtime_c/primitives_sequence_functions.h>
#include <rosidl_runtime_c/string_functions.h>
#include <sensor_msgs/msg/imu.h>
#include <sensor_msgs/msg/joint_state.h>
#include <std_msgs/msg/bool.h>
#include <std_msgs/msg/u_int32.h>

#include "wifi_config.h"

// Physical constants and corrected pin mapping are copied from PID/PID.
constexpr float WHEEL_RADIUS_M = 0.0485f;
constexpr float LX_M = 0.395f / 2.0f;
constexpr float LY_M = 0.4545f / 2.0f;
constexpr float K_M = LX_M + LY_M;
constexpr float ENCODER_PPR = 4080.0f;

constexpr uint32_t CONTROL_PERIOD_MS = 20;
constexpr float CONTROL_DT_S = CONTROL_PERIOD_MS / 1000.0f;
constexpr uint32_t IMU_PERIOD_MS = 10;
constexpr uint32_t COMMAND_TIMEOUT_MS = 500;
constexpr uint32_t AGENT_DISCOVERY_PERIOD_MS = 500;
constexpr uint32_t AGENT_HEALTH_PERIOD_MS = 1000;
constexpr uint8_t IMU_FAILURE_LIMIT = 5;
constexpr float FILTER_ALPHA = 0.25f;

constexpr float MAX_VX_MPS = 0.20f;
constexpr float MAX_VY_MPS = 0.20f;
constexpr float MAX_WZ_RAD_S = 0.80f;

constexpr uint32_t PWM_FREQ_HZ = 20000;
constexpr uint8_t PWM_RESOLUTION = 8;
constexpr int PWM_ABS_LIMIT = 255;

#define FR_PWM 18
#define FR_DIR1 5
#define FR_DIR2 17
#define FR_ENC_A 34
#define FR_ENC_B 35

#define FL_PWM 19
#define FL_DIR1 33
#define FL_DIR2 32
#define FL_ENC_A 39
#define FL_ENC_B 36

#define RR_PWM 4
#define RR_DIR1 16
#define RR_DIR2 2
#define RR_ENC_A 26
#define RR_ENC_B 25

#define RL_PWM 13
#define RL_DIR1 15
#define RL_DIR2 23
#define RL_ENC_A 14
#define RL_ENC_B 27

#define I2C_SDA_PIN 21
#define I2C_SCL_PIN 22

#define BMI160_ADDR_1 0x68
#define BMI160_ADDR_2 0x69
#define BMI160_REG_CHIP_ID 0x00
#define BMI160_REG_PMU_STATUS 0x03
#define BMI160_REG_GYR_X_LSB 0x0C
#define BMI160_REG_ACC_RANGE 0x41
#define BMI160_REG_GYR_RANGE 0x43
#define BMI160_REG_CMD 0x7E
#define BMI160_CMD_ACC_NORMAL 0x11
#define BMI160_CMD_GYR_NORMAL 0x15
#define BMI160_CMD_SOFT_RESET 0xB6

constexpr float BMI160_GYRO_LSB_PER_DPS = 131.2f;
constexpr float DEG_TO_RAD_F = PI / 180.0f;

struct Wheel {
  const char *name;
  int pwm_pin;
  int pwm_channel;
  int dir1_pin;
  int dir2_pin;
  int enc_a_pin;
  int enc_b_pin;
  volatile int32_t *encoder_count;
  volatile uint8_t *last_encoder_state;
  int32_t last_count;
  float raw_rad_s;
  float filtered_rad_s;
  float target_rad_s;
  float kp;
  float ki;
  float kd;
  int base_pwm;
  int max_pwm;
  float integral;
  float last_error;
  float integral_limit;
  int applied_pwm;
};

volatile int32_t encoder_fr = 0;
volatile int32_t encoder_fl = 0;
volatile int32_t encoder_rr = 0;
volatile int32_t encoder_rl = 0;

volatile uint8_t fr_last_state = 0;
volatile uint8_t fl_last_state = 0;
volatile uint8_t rr_last_state = 0;
volatile uint8_t rl_last_state = 0;

Wheel wheel_fr = {
    "front_right_wheel_joint", FR_PWM, 0, FR_DIR1, FR_DIR2, FR_ENC_A, FR_ENC_B,
    &encoder_fr, &fr_last_state, 0, 0.0f, 0.0f, 0.0f,
    105.0f, 40.0f, 0.0f, 30, 150, 0.0f, 0.0f, 50.0f, 0};

Wheel wheel_fl = {
    "front_left_wheel_joint", FL_PWM, 1, FL_DIR1, FL_DIR2, FL_ENC_A, FL_ENC_B,
    &encoder_fl, &fl_last_state, 0, 0.0f, 0.0f, 0.0f,
    100.0f, 50.0f, 0.0f, 30, 150, 0.0f, 0.0f, 50.0f, 0};

Wheel wheel_rr = {
    "rear_right_wheel_joint", RR_PWM, 2, RR_DIR1, RR_DIR2, RR_ENC_A, RR_ENC_B,
    &encoder_rr, &rr_last_state, 0, 0.0f, 0.0f, 0.0f,
    100.0f, 40.0f, 0.0f, 30, 150, 0.0f, 0.0f, 50.0f, 0};

Wheel wheel_rl = {
    "rear_left_wheel_joint", RL_PWM, 3, RL_DIR1, RL_DIR2, RL_ENC_A, RL_ENC_B,
    &encoder_rl, &rl_last_state, 0, 0.0f, 0.0f, 0.0f,
    100.0f, 20.0f, 0.0f, 30, 150, 0.0f, 0.0f, 50.0f, 0};

portMUX_TYPE command_mux = portMUX_INITIALIZER_UNLOCKED;
portMUX_TYPE telemetry_mux = portMUX_INITIALIZER_UNLOCKED;
portMUX_TYPE imu_mux = portMUX_INITIALIZER_UNLOCKED;

float requested_vx = 0.0f;
float requested_vy = 0.0f;
float requested_wz = 0.0f;
bool base_enabled = false;
uint32_t last_cmd_vel_ms = 0;

float telemetry_velocity[4] = {0.0f, 0.0f, 0.0f, 0.0f};
int32_t telemetry_counts[4] = {0, 0, 0, 0};

uint8_t bmi_address = BMI160_ADDR_1;
bool imu_initialized = false;
bool imu_ok = false;
float gyro_bias_x_dps = 0.0f;
float gyro_bias_y_dps = 0.0f;
float gyro_bias_z_dps = 0.0f;
double gyro_variance_x_rad_s = 0.0;
double gyro_variance_y_rad_s = 0.0;
double gyro_variance_z_rad_s = 0.0;
float gyro_x_rad_s = 0.0f;
float gyro_y_rad_s = 0.0f;
float gyro_z_rad_s = 0.0f;

rcl_allocator_t allocator;
rclc_support_t support;
rcl_node_t node;
rcl_publisher_t wheel_states_publisher;
rcl_publisher_t imu_publisher;
rcl_publisher_t imu_ok_publisher;
rcl_publisher_t heartbeat_publisher;
rcl_subscription_t cmd_vel_subscription;
rcl_subscription_t enable_subscription;
rcl_timer_t telemetry_timer;
rclc_executor_t executor;

geometry_msgs__msg__Twist cmd_vel_message;
std_msgs__msg__Bool enable_message;
sensor_msgs__msg__JointState wheel_states_message;
sensor_msgs__msg__Imu imu_message;
std_msgs__msg__Bool imu_ok_message;
std_msgs__msg__UInt32 heartbeat_message;

enum AgentState {
  WAITING_FOR_AGENT,
  AGENT_AVAILABLE,
  AGENT_CONNECTED,
  AGENT_DISCONNECTED
};

volatile AgentState agent_state = WAITING_FOR_AGENT;
bool messages_initialized = false;
bool support_initialized = false;
bool node_initialized = false;
bool wheel_publisher_initialized = false;
bool imu_publisher_initialized = false;
bool imu_ok_publisher_initialized = false;
bool heartbeat_publisher_initialized = false;
bool cmd_vel_subscription_initialized = false;
bool enable_subscription_initialized = false;
bool telemetry_timer_initialized = false;
bool executor_initialized = false;

bool i2cWrite8(uint8_t address, uint8_t reg, uint8_t value) {
  Wire.beginTransmission(address);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool i2cReadBytes(uint8_t address, uint8_t reg, uint8_t *data, uint8_t length) {
  Wire.beginTransmission(address);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  if (Wire.requestFrom(address, length) != length) {
    return false;
  }

  for (uint8_t index = 0; index < length; ++index) {
    data[index] = Wire.read();
  }
  return true;
}

uint8_t i2cRead8(uint8_t address, uint8_t reg) {
  uint8_t value = 0xFF;
  i2cReadBytes(address, reg, &value, 1);
  return value;
}

bool bmi160Detect() {
  if (i2cRead8(BMI160_ADDR_1, BMI160_REG_CHIP_ID) == 0xD1) {
    bmi_address = BMI160_ADDR_1;
    return true;
  }
  if (i2cRead8(BMI160_ADDR_2, BMI160_REG_CHIP_ID) == 0xD1) {
    bmi_address = BMI160_ADDR_2;
    return true;
  }
  return false;
}

bool bmi160ReadGyro(float &gx_dps, float &gy_dps, float &gz_dps) {
  uint8_t data[6];
  if (!i2cReadBytes(bmi_address, BMI160_REG_GYR_X_LSB, data, 6)) {
    return false;
  }

  const int16_t raw_x = static_cast<int16_t>((data[1] << 8) | data[0]);
  const int16_t raw_y = static_cast<int16_t>((data[3] << 8) | data[2]);
  const int16_t raw_z = static_cast<int16_t>((data[5] << 8) | data[4]);
  gx_dps = static_cast<float>(raw_x) / BMI160_GYRO_LSB_PER_DPS;
  gy_dps = static_cast<float>(raw_y) / BMI160_GYRO_LSB_PER_DPS;
  gz_dps = static_cast<float>(raw_z) / BMI160_GYRO_LSB_PER_DPS;
  return true;
}

bool bmi160Init() {
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  Wire.setClock(400000);
  delay(100);

  if (!bmi160Detect()) {
    return false;
  }

  i2cWrite8(bmi_address, BMI160_REG_CMD, BMI160_CMD_SOFT_RESET);
  delay(100);
  if (!bmi160Detect()) {
    return false;
  }

  i2cWrite8(bmi_address, BMI160_REG_CMD, BMI160_CMD_ACC_NORMAL);
  delay(50);
  i2cWrite8(bmi_address, BMI160_REG_CMD, BMI160_CMD_GYR_NORMAL);
  delay(100);
  i2cWrite8(bmi_address, BMI160_REG_ACC_RANGE, 0x03);
  i2cWrite8(bmi_address, BMI160_REG_GYR_RANGE, 0x03);
  delay(20);
  return true;
}

bool calibrateGyro(uint16_t samples) {
  double sum_x = 0.0;
  double sum_y = 0.0;
  double sum_z = 0.0;
  double sum_square_x = 0.0;
  double sum_square_y = 0.0;
  double sum_square_z = 0.0;
  uint16_t valid_samples = 0;

  for (uint16_t index = 0; index < samples; ++index) {
    float gx = 0.0f;
    float gy = 0.0f;
    float gz = 0.0f;
    if (bmi160ReadGyro(gx, gy, gz)) {
      sum_x += gx;
      sum_y += gy;
      sum_z += gz;
      sum_square_x += static_cast<double>(gx) * gx;
      sum_square_y += static_cast<double>(gy) * gy;
      sum_square_z += static_cast<double>(gz) * gz;
      ++valid_samples;
    }
    delay(5);
  }

  if (valid_samples < samples / 2) {
    return false;
  }

  gyro_bias_x_dps = sum_x / valid_samples;
  gyro_bias_y_dps = sum_y / valid_samples;
  gyro_bias_z_dps = sum_z / valid_samples;

  const double sample_count = static_cast<double>(valid_samples);
  const double degrees_to_radians_squared =
      static_cast<double>(DEG_TO_RAD_F) * DEG_TO_RAD_F;
  const double variance_x_dps =
      (sum_square_x - (sum_x * sum_x / sample_count)) /
      (sample_count - 1.0);
  const double variance_y_dps =
      (sum_square_y - (sum_y * sum_y / sample_count)) /
      (sample_count - 1.0);
  const double variance_z_dps =
      (sum_square_z - (sum_z * sum_z / sample_count)) /
      (sample_count - 1.0);

  gyro_variance_x_rad_s =
      fmax(variance_x_dps * degrees_to_radians_squared, 1.0e-9);
  gyro_variance_y_rad_s =
      fmax(variance_y_dps * degrees_to_radians_squared, 1.0e-9);
  gyro_variance_z_rad_s =
      fmax(variance_z_dps * degrees_to_radians_squared, 1.0e-9);
  return true;
}

void IRAM_ATTR updateQuadrature(
    int enc_a_pin,
    int enc_b_pin,
    volatile int32_t *count,
    volatile uint8_t *last_state) {
  const uint8_t a = digitalRead(enc_a_pin);
  const uint8_t b = digitalRead(enc_b_pin);
  const uint8_t state = (a << 1) | b;
  const uint8_t transition = ((*last_state) << 2) | state;

  if (transition == 0b0001 || transition == 0b0111 ||
      transition == 0b1110 || transition == 0b1000) {
    ++(*count);
  } else if (transition == 0b0010 || transition == 0b1011 ||
             transition == 0b1101 || transition == 0b0100) {
    --(*count);
  }
  *last_state = state;
}

void IRAM_ATTR isrFR() {
  updateQuadrature(FR_ENC_A, FR_ENC_B, &encoder_fr, &fr_last_state);
}
void IRAM_ATTR isrFL() {
  updateQuadrature(FL_ENC_A, FL_ENC_B, &encoder_fl, &fl_last_state);
}
void IRAM_ATTR isrRR() {
  updateQuadrature(RR_ENC_A, RR_ENC_B, &encoder_rr, &rr_last_state);
}
void IRAM_ATTR isrRL() {
  updateQuadrature(RL_ENC_A, RL_ENC_B, &encoder_rl, &rl_last_state);
}

void setWheelPwm(Wheel &wheel, int pwm) {
  pwm = constrain(pwm, -PWM_ABS_LIMIT, PWM_ABS_LIMIT);
  wheel.applied_pwm = pwm;

  if (pwm > 0) {
    digitalWrite(wheel.dir1_pin, HIGH);
    digitalWrite(wheel.dir2_pin, LOW);
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    ledcWrite(wheel.pwm_pin, pwm);
#else
    ledcWrite(wheel.pwm_channel, pwm);
#endif
  } else if (pwm < 0) {
    digitalWrite(wheel.dir1_pin, LOW);
    digitalWrite(wheel.dir2_pin, HIGH);
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    ledcWrite(wheel.pwm_pin, -pwm);
#else
    ledcWrite(wheel.pwm_channel, -pwm);
#endif
  } else {
    digitalWrite(wheel.dir1_pin, LOW);
    digitalWrite(wheel.dir2_pin, LOW);
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    ledcWrite(wheel.pwm_pin, 0);
#else
    ledcWrite(wheel.pwm_channel, 0);
#endif
  }
}

void resetWheelPid(Wheel &wheel) {
  wheel.integral = 0.0f;
  wheel.last_error = 0.0f;
}

void stopAllMotors() {
  wheel_fl.target_rad_s = 0.0f;
  wheel_fr.target_rad_s = 0.0f;
  wheel_rl.target_rad_s = 0.0f;
  wheel_rr.target_rad_s = 0.0f;

  resetWheelPid(wheel_fl);
  resetWheelPid(wheel_fr);
  resetWheelPid(wheel_rl);
  resetWheelPid(wheel_rr);

  setWheelPwm(wheel_fl, 0);
  setWheelPwm(wheel_fr, 0);
  setWheelPwm(wheel_rl, 0);
  setWheelPwm(wheel_rr, 0);
}

float countsToRadS(int32_t delta_counts) {
  return (static_cast<float>(delta_counts) / ENCODER_PPR) *
         2.0f * PI / CONTROL_DT_S;
}

void updateWheelSpeed(Wheel &wheel) {
  noInterrupts();
  const int32_t current_count = *(wheel.encoder_count);
  interrupts();

  const int32_t delta = current_count - wheel.last_count;
  wheel.last_count = current_count;
  wheel.raw_rad_s = countsToRadS(delta);
  wheel.filtered_rad_s =
      FILTER_ALPHA * wheel.raw_rad_s +
      (1.0f - FILTER_ALPHA) * wheel.filtered_rad_s;
}

void updateWheelPid(Wheel &wheel) {
  if (fabsf(wheel.target_rad_s) < 0.01f) {
    resetWheelPid(wheel);
    setWheelPwm(wheel, 0);
    return;
  }

  const float error = wheel.target_rad_s - wheel.filtered_rad_s;
  wheel.integral += error * CONTROL_DT_S;
  wheel.integral =
      constrain(wheel.integral, -wheel.integral_limit, wheel.integral_limit);

  const float derivative = (error - wheel.last_error) / CONTROL_DT_S;
  wheel.last_error = error;
  const float pid_output =
      wheel.kp * error + wheel.ki * wheel.integral + wheel.kd * derivative;

  int feedforward = 0;
  if (wheel.target_rad_s > 0.0f) {
    feedforward = wheel.base_pwm;
  } else if (wheel.target_rad_s < 0.0f) {
    feedforward = -wheel.base_pwm;
  }

  const int pwm_command = constrain(
      feedforward + static_cast<int>(pid_output),
      -wheel.max_pwm,
      wheel.max_pwm);
  setWheelPwm(wheel, pwm_command);
}

void setBodyVelocityTargets(float vx, float vy, float wz) {
  wheel_fl.target_rad_s = (vx - vy - K_M * wz) / WHEEL_RADIUS_M;
  wheel_fr.target_rad_s = (vx + vy + K_M * wz) / WHEEL_RADIUS_M;
  wheel_rl.target_rad_s = (vx + vy - K_M * wz) / WHEEL_RADIUS_M;
  wheel_rr.target_rad_s = (vx - vy + K_M * wz) / WHEEL_RADIUS_M;
}

void setupWheelPins(Wheel &wheel) {
  pinMode(wheel.dir1_pin, OUTPUT);
  pinMode(wheel.dir2_pin, OUTPUT);
  pinMode(wheel.enc_a_pin, INPUT);
  pinMode(wheel.enc_b_pin, INPUT);
  digitalWrite(wheel.dir1_pin, LOW);
  digitalWrite(wheel.dir2_pin, LOW);

#if ESP_ARDUINO_VERSION_MAJOR >= 3
  const bool pwm_ready =
      ledcAttach(wheel.pwm_pin, PWM_FREQ_HZ, PWM_RESOLUTION);
#else
  const bool pwm_ready =
      ledcSetup(
          wheel.pwm_channel, PWM_FREQ_HZ, PWM_RESOLUTION) > 0.0;
  if (pwm_ready) {
    ledcAttachPin(wheel.pwm_pin, wheel.pwm_channel);
  }
#endif
  if (!pwm_ready) {
    while (true) {
      delay(1000);
    }
  }
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(wheel.pwm_pin, 0);
#else
  ledcWrite(wheel.pwm_channel, 0);
#endif
  *(wheel.last_encoder_state) =
      (digitalRead(wheel.enc_a_pin) << 1) | digitalRead(wheel.enc_b_pin);
}

void cmdVelCallback(const void *message) {
  const auto *cmd = static_cast<const geometry_msgs__msg__Twist *>(message);
  portENTER_CRITICAL(&command_mux);
  requested_vx = constrain(
      static_cast<float>(cmd->linear.x), -MAX_VX_MPS, MAX_VX_MPS);
  requested_vy = constrain(
      static_cast<float>(cmd->linear.y), -MAX_VY_MPS, MAX_VY_MPS);
  requested_wz = constrain(
      static_cast<float>(cmd->angular.z), -MAX_WZ_RAD_S, MAX_WZ_RAD_S);
  last_cmd_vel_ms = millis();
  portEXIT_CRITICAL(&command_mux);
}

void enableCallback(const void *message) {
  const auto *enabled = static_cast<const std_msgs__msg__Bool *>(message);
  portENTER_CRITICAL(&command_mux);
  base_enabled = enabled->data;
  if (!base_enabled) {
    requested_vx = 0.0f;
    requested_vy = 0.0f;
    requested_wz = 0.0f;
    last_cmd_vel_ms = 0;
  }
  portEXIT_CRITICAL(&command_mux);
}

void fillStamp(std_msgs__msg__Header &header) {
  const int64_t epoch_nanos = rmw_uros_epoch_nanos();
  if (epoch_nanos > 0) {
    header.stamp.sec = static_cast<int32_t>(epoch_nanos / 1000000000LL);
    header.stamp.nanosec =
        static_cast<uint32_t>(epoch_nanos % 1000000000LL);
  } else {
    header.stamp.sec = 0;
    header.stamp.nanosec = 0;
  }
}

void telemetryTimerCallback(rcl_timer_t *timer, int64_t) {
  if (timer == nullptr) {
    return;
  }

  portENTER_CRITICAL(&telemetry_mux);
  for (size_t index = 0; index < 4; ++index) {
    wheel_states_message.velocity.data[index] = telemetry_velocity[index];
    wheel_states_message.position.data[index] =
        (static_cast<double>(telemetry_counts[index]) / ENCODER_PPR) *
        2.0 * PI;
  }
  portEXIT_CRITICAL(&telemetry_mux);
  fillStamp(wheel_states_message.header);
  rcl_publish(&wheel_states_publisher, &wheel_states_message, nullptr);

  portENTER_CRITICAL(&imu_mux);
  imu_message.angular_velocity.x = gyro_x_rad_s;
  imu_message.angular_velocity.y = gyro_y_rad_s;
  imu_message.angular_velocity.z = gyro_z_rad_s;
  imu_ok_message.data = imu_ok;
  const bool publish_imu = imu_ok;
  portEXIT_CRITICAL(&imu_mux);
  if (publish_imu) {
    fillStamp(imu_message.header);
    rcl_publish(&imu_publisher, &imu_message, nullptr);
  }

  static uint8_t status_divider = 0;
  if (++status_divider >= 50) {
    status_divider = 0;
    ++heartbeat_message.data;
    rcl_publish(&imu_ok_publisher, &imu_ok_message, nullptr);
    rcl_publish(&heartbeat_publisher, &heartbeat_message, nullptr);
  }
}

bool initializeMessages() {
  if (messages_initialized) {
    return true;
  }

  if (!sensor_msgs__msg__JointState__init(&wheel_states_message) ||
      !sensor_msgs__msg__Imu__init(&imu_message)) {
    return false;
  }

  if (!rosidl_runtime_c__String__assign(
          &wheel_states_message.header.frame_id, "") ||
      !rosidl_runtime_c__String__assign(
          &imu_message.header.frame_id, "base_link") ||
      !rosidl_runtime_c__String__Sequence__init(
          &wheel_states_message.name, 4) ||
      !rosidl_runtime_c__double__Sequence__init(
          &wheel_states_message.position, 4) ||
      !rosidl_runtime_c__double__Sequence__init(
          &wheel_states_message.velocity, 4)) {
    return false;
  }

  const char *names[4] = {
      wheel_fl.name, wheel_fr.name, wheel_rl.name, wheel_rr.name};
  for (size_t index = 0; index < 4; ++index) {
    if (!rosidl_runtime_c__String__assign(
            &wheel_states_message.name.data[index], names[index])) {
      return false;
    }
  }

  imu_message.orientation_covariance[0] = -1.0;
  imu_message.linear_acceleration_covariance[0] = -1.0;
  for (double &value : imu_message.angular_velocity_covariance) {
    value = 0.0;
  }
  imu_message.angular_velocity_covariance[0] = gyro_variance_x_rad_s;
  imu_message.angular_velocity_covariance[4] = gyro_variance_y_rad_s;
  imu_message.angular_velocity_covariance[8] = gyro_variance_z_rad_s;

  heartbeat_message.data = 0;
  messages_initialized = true;
  return true;
}

void resetEntityHandles() {
  support = rclc_support_t{};
  node = rcl_get_zero_initialized_node();
  wheel_states_publisher = rcl_get_zero_initialized_publisher();
  imu_publisher = rcl_get_zero_initialized_publisher();
  imu_ok_publisher = rcl_get_zero_initialized_publisher();
  heartbeat_publisher = rcl_get_zero_initialized_publisher();
  cmd_vel_subscription = rcl_get_zero_initialized_subscription();
  enable_subscription = rcl_get_zero_initialized_subscription();
  telemetry_timer = rcl_get_zero_initialized_timer();
  executor = rclc_executor_t{};
}

bool createEntities() {
  resetEntityHandles();
  allocator = rcl_get_default_allocator();
  if (rclc_support_init(&support, 0, nullptr, &allocator) != RCL_RET_OK) {
    return false;
  }
  support_initialized = true;

  if (rclc_node_init_default(
          &node, "esp32_base_node", "", &support) != RCL_RET_OK) {
    return false;
  }
  node_initialized = true;

  if (rclc_publisher_init_best_effort(
          &wheel_states_publisher,
          &node,
          ROSIDL_GET_MSG_TYPE_SUPPORT(sensor_msgs, msg, JointState),
          "/base/wheel_states") != RCL_RET_OK) {
    return false;
  }
  wheel_publisher_initialized = true;

  if (rclc_publisher_init_best_effort(
          &imu_publisher,
          &node,
          ROSIDL_GET_MSG_TYPE_SUPPORT(sensor_msgs, msg, Imu),
          "/imu/data_raw") != RCL_RET_OK) {
    return false;
  }
  imu_publisher_initialized = true;

  if (rclc_publisher_init_default(
          &imu_ok_publisher,
          &node,
          ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Bool),
          "/base/imu_ok") != RCL_RET_OK) {
    return false;
  }
  imu_ok_publisher_initialized = true;

  if (rclc_publisher_init_best_effort(
          &heartbeat_publisher,
          &node,
          ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, UInt32),
          "/base/heartbeat") != RCL_RET_OK) {
    return false;
  }
  heartbeat_publisher_initialized = true;

  if (rclc_subscription_init_best_effort(
          &cmd_vel_subscription,
          &node,
          ROSIDL_GET_MSG_TYPE_SUPPORT(geometry_msgs, msg, Twist),
          "/cmd_vel") != RCL_RET_OK) {
    return false;
  }
  cmd_vel_subscription_initialized = true;

  if (rclc_subscription_init_default(
          &enable_subscription,
          &node,
          ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Bool),
          "/base/enable") != RCL_RET_OK) {
    return false;
  }
  enable_subscription_initialized = true;

  if (rclc_timer_init_default(
          &telemetry_timer,
          &support,
          RCL_MS_TO_NS(CONTROL_PERIOD_MS),
          telemetryTimerCallback) != RCL_RET_OK) {
    return false;
  }
  telemetry_timer_initialized = true;

  if (rclc_executor_init(
          &executor, &support.context, 3, &allocator) != RCL_RET_OK) {
    return false;
  }
  executor_initialized = true;

  if (rclc_executor_add_subscription(
          &executor,
          &cmd_vel_subscription,
          &cmd_vel_message,
          &cmdVelCallback,
          ON_NEW_DATA) != RCL_RET_OK) {
    return false;
  }

  if (rclc_executor_add_subscription(
          &executor,
          &enable_subscription,
          &enable_message,
          &enableCallback,
          ON_NEW_DATA) != RCL_RET_OK) {
    return false;
  }

  if (rclc_executor_add_timer(
          &executor, &telemetry_timer) != RCL_RET_OK) {
    return false;
  }

  rmw_uros_sync_session(1000);
  return true;
}

void destroyEntities() {
  if (support_initialized) {
    rmw_context_t *rmw_context =
        rcl_context_get_rmw_context(&support.context);
    rmw_uros_set_context_entity_destroy_session_timeout(rmw_context, 0);
  }

  if (executor_initialized) {
    rclc_executor_fini(&executor);
    executor_initialized = false;
  }
  if (telemetry_timer_initialized) {
    rcl_timer_fini(&telemetry_timer);
    telemetry_timer_initialized = false;
  }
  if (cmd_vel_subscription_initialized) {
    rcl_subscription_fini(&cmd_vel_subscription, &node);
    cmd_vel_subscription_initialized = false;
  }
  if (enable_subscription_initialized) {
    rcl_subscription_fini(&enable_subscription, &node);
    enable_subscription_initialized = false;
  }
  if (wheel_publisher_initialized) {
    rcl_publisher_fini(&wheel_states_publisher, &node);
    wheel_publisher_initialized = false;
  }
  if (imu_publisher_initialized) {
    rcl_publisher_fini(&imu_publisher, &node);
    imu_publisher_initialized = false;
  }
  if (imu_ok_publisher_initialized) {
    rcl_publisher_fini(&imu_ok_publisher, &node);
    imu_ok_publisher_initialized = false;
  }
  if (heartbeat_publisher_initialized) {
    rcl_publisher_fini(&heartbeat_publisher, &node);
    heartbeat_publisher_initialized = false;
  }
  if (node_initialized) {
    rcl_node_fini(&node);
    node_initialized = false;
  }
  if (support_initialized) {
    rclc_support_fini(&support);
    support_initialized = false;
  }

  portENTER_CRITICAL(&command_mux);
  base_enabled = false;
  requested_vx = 0.0f;
  requested_vy = 0.0f;
  requested_wz = 0.0f;
  last_cmd_vel_ms = 0;
  portEXIT_CRITICAL(&command_mux);
}

void controlTask(void *) {
  TickType_t last_wake = xTaskGetTickCount();

  while (true) {
    updateWheelSpeed(wheel_fl);
    updateWheelSpeed(wheel_fr);
    updateWheelSpeed(wheel_rl);
    updateWheelSpeed(wheel_rr);

    float vx = 0.0f;
    float vy = 0.0f;
    float wz = 0.0f;
    bool enabled = false;
    uint32_t last_command = 0;

    portENTER_CRITICAL(&command_mux);
    vx = requested_vx;
    vy = requested_vy;
    wz = requested_wz;
    enabled = base_enabled;
    last_command = last_cmd_vel_ms;
    portEXIT_CRITICAL(&command_mux);

    const bool command_fresh =
        last_command != 0 &&
        static_cast<uint32_t>(millis() - last_command) <= COMMAND_TIMEOUT_MS;

    if (enabled && command_fresh && agent_state == AGENT_CONNECTED) {
      setBodyVelocityTargets(vx, vy, wz);
    } else {
      setBodyVelocityTargets(0.0f, 0.0f, 0.0f);
    }

    updateWheelPid(wheel_fl);
    updateWheelPid(wheel_fr);
    updateWheelPid(wheel_rl);
    updateWheelPid(wheel_rr);

    noInterrupts();
    const int32_t fl_count = encoder_fl;
    const int32_t fr_count = encoder_fr;
    const int32_t rl_count = encoder_rl;
    const int32_t rr_count = encoder_rr;
    interrupts();

    portENTER_CRITICAL(&telemetry_mux);
    telemetry_velocity[0] = wheel_fl.filtered_rad_s;
    telemetry_velocity[1] = wheel_fr.filtered_rad_s;
    telemetry_velocity[2] = wheel_rl.filtered_rad_s;
    telemetry_velocity[3] = wheel_rr.filtered_rad_s;
    telemetry_counts[0] = fl_count;
    telemetry_counts[1] = fr_count;
    telemetry_counts[2] = rl_count;
    telemetry_counts[3] = rr_count;
    portEXIT_CRITICAL(&telemetry_mux);

    vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(CONTROL_PERIOD_MS));
  }
}

void imuTask(void *) {
  TickType_t last_wake = xTaskGetTickCount();
  uint8_t consecutive_failures = 0;

  while (true) {
    float gx_dps = 0.0f;
    float gy_dps = 0.0f;
    float gz_dps = 0.0f;
    const bool read_ok =
        imu_initialized && bmi160ReadGyro(gx_dps, gy_dps, gz_dps);

    portENTER_CRITICAL(&imu_mux);
    if (read_ok) {
      consecutive_failures = 0;
      imu_ok = true;
      gyro_x_rad_s = (gx_dps - gyro_bias_x_dps) * DEG_TO_RAD_F;
      gyro_y_rad_s = (gy_dps - gyro_bias_y_dps) * DEG_TO_RAD_F;
      gyro_z_rad_s = (gz_dps - gyro_bias_z_dps) * DEG_TO_RAD_F;
    } else if (
        consecutive_failures < IMU_FAILURE_LIMIT &&
        ++consecutive_failures >= IMU_FAILURE_LIMIT) {
      imu_ok = false;
      gyro_x_rad_s = 0.0f;
      gyro_y_rad_s = 0.0f;
      gyro_z_rad_s = 0.0f;
    }
    portEXIT_CRITICAL(&imu_mux);

    vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(IMU_PERIOD_MS));
  }
}

void microRosTask(void *) {
  uint32_t last_discovery_ms = 0;
  uint32_t last_health_check_ms = 0;

  while (true) {
    const uint32_t now_ms = millis();
    switch (agent_state) {
      case WAITING_FOR_AGENT:
        if (static_cast<uint32_t>(now_ms - last_discovery_ms) <
            AGENT_DISCOVERY_PERIOD_MS) {
          break;
        }
        last_discovery_ms = now_ms;
        if (rmw_uros_ping_agent(100, 1) == RMW_RET_OK) {
          agent_state = AGENT_AVAILABLE;
        }
        break;

      case AGENT_AVAILABLE:
        if (createEntities()) {
          last_health_check_ms = now_ms;
          agent_state = AGENT_CONNECTED;
        } else {
          destroyEntities();
          agent_state = WAITING_FOR_AGENT;
        }
        break;

      case AGENT_CONNECTED:
        rclc_executor_spin_some(&executor, RCL_MS_TO_NS(5));
        if (static_cast<uint32_t>(now_ms - last_health_check_ms) <
            AGENT_HEALTH_PERIOD_MS) {
          break;
        }
        last_health_check_ms = now_ms;
        if (rmw_uros_ping_agent(50, 1) != RMW_RET_OK) {
          agent_state = AGENT_DISCONNECTED;
        }
        break;

      case AGENT_DISCONNECTED:
        destroyEntities();
        agent_state = WAITING_FOR_AGENT;
        break;
    }
    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);

  setupWheelPins(wheel_fl);
  setupWheelPins(wheel_fr);
  setupWheelPins(wheel_rl);
  setupWheelPins(wheel_rr);

  attachInterrupt(digitalPinToInterrupt(FR_ENC_A), isrFR, CHANGE);
  attachInterrupt(digitalPinToInterrupt(FR_ENC_B), isrFR, CHANGE);
  attachInterrupt(digitalPinToInterrupt(FL_ENC_A), isrFL, CHANGE);
  attachInterrupt(digitalPinToInterrupt(FL_ENC_B), isrFL, CHANGE);
  attachInterrupt(digitalPinToInterrupt(RR_ENC_A), isrRR, CHANGE);
  attachInterrupt(digitalPinToInterrupt(RR_ENC_B), isrRR, CHANGE);
  attachInterrupt(digitalPinToInterrupt(RL_ENC_A), isrRL, CHANGE);
  attachInterrupt(digitalPinToInterrupt(RL_ENC_B), isrRL, CHANGE);
  stopAllMotors();

  imu_initialized = bmi160Init();
  if (imu_initialized) {
    imu_initialized = calibrateGyro(1200);
  }
  imu_ok = imu_initialized;

  if (!initializeMessages()) {
    while (true) {
      stopAllMotors();
      delay(1000);
    }
  }

  const IPAddress local_ip(
      MOTIVON_ESP_IP_0,
      MOTIVON_ESP_IP_1,
      MOTIVON_ESP_IP_2,
      MOTIVON_ESP_IP_3);
  const IPAddress gateway(
      MOTIVON_GATEWAY_IP_0,
      MOTIVON_GATEWAY_IP_1,
      MOTIVON_GATEWAY_IP_2,
      MOTIVON_GATEWAY_IP_3);
  const IPAddress subnet(255, 255, 255, 0);
  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
  WiFi.setSleep(false);
  WiFi.config(local_ip, gateway, subnet);
  set_microros_wifi_transports(
      const_cast<char *>(MOTIVON_WIFI_SSID),
      const_cast<char *>(MOTIVON_WIFI_PASSWORD),
      const_cast<char *>(MOTIVON_AGENT_IP),
      MOTIVON_AGENT_PORT);

  xTaskCreatePinnedToCore(
      controlTask, "motor_control", 4096, nullptr, 4, nullptr, 1);
  xTaskCreatePinnedToCore(
      imuTask, "imu_sampling", 4096, nullptr, 3, nullptr, 1);
  xTaskCreatePinnedToCore(
      microRosTask, "micro_ros", 12288, nullptr, 2, nullptr, 0);
}

void loop() {
  vTaskDelay(portMAX_DELAY);
}
