#include <Arduino.h>
#include <Wire.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"

/*
  ============================================================
  DELIVERY ROBOT - RAW PID + ODOMETRY + YAW HOLD

  Added:
    - BMI160 IMU over I2C
    - ESP32 SDA = 21, SCL = 22
    - Yaw estimation from gyro Z
    - Active yaw hold during position control

  Serial Monitor:
    Baud: 115200
    Line ending: Newline

  Main motion:
    pos 1.00
    pos -1.00
    vel 0.08
    stop
    reset
    show
    help
    cal 0.53
    cal2 1.011 0.53
    odomreset

  IMU / Yaw:
    imucal          -> keep robot still, calibrates gyro Z bias
    yawzero         -> sets current yaw as 0 degrees
    imu             -> prints IMU status
    yawhold 1       -> enable yaw hold
    yawhold 0       -> disable yaw hold
    yawkp 2.0
    yawki 0.0
    yawkd 0.08
    yawmax 0.35
    yawtol 2.0
    yawsign 1
    yawsign -1

  Odometry:
    odom 0.9907
    cal 0.53              -> use current displayed x and real measured distance
    cal2 1.011 0.53       -> displayed x, real measured distance
    odomreset             -> reset x odometry only

  Wheel trims:
    trims 1.00 1.00 1.00 1.00
    trim fr 1.05
  ============================================================
*/

// ============================================================
// Robot Geometry
// ============================================================

const float WHEEL_RADIUS_M = 0.0485f;
const float LX_M = 0.395f / 2.0f;
const float LY_M = 0.4545f / 2.0f;
const float K_M = LX_M + LY_M;

// ============================================================
// Encoder / PWM Settings
// ============================================================

const float ENCODER_PPR = 1020.0f;

const uint32_t PWM_FREQ_HZ = 20000;
const uint8_t PWM_RESOLUTION = 8;
const float PWM_MAX = 255.0f;

float GROUND_PWM_LIMIT = 120.0f;
float MAX_PWM_STEP = 12.0f;

const uint32_t CONTROL_DT_MS = 100;
const float CONTROL_DT_S = 0.100f;

float MAX_VALID_RAD_S = 30.0f;
float MAX_JUMP_RAD_S = 4.0f;
float RAW_ZERO_EPS = 0.30f;
float OPPOSITE_SIGN_REJECT_RAD_S = 4.0f;

float alpha = 0.25f;
float ZERO_SPEED_EPS = 0.05f;

// ============================================================
// BMI160 IMU Settings
// ============================================================

#define I2C_SDA_PIN 21
#define I2C_SCL_PIN 22

#define BMI160_ADDR_1 0x68
#define BMI160_ADDR_2 0x69

#define BMI160_REG_CHIP_ID    0x00
#define BMI160_REG_PMU_STATUS 0x03
#define BMI160_REG_GYR_X_LSB  0x0C
#define BMI160_REG_GYR_Z_LSB  0x10
#define BMI160_REG_ACC_X_LSB  0x12
#define BMI160_REG_ACC_RANGE  0x41
#define BMI160_REG_GYR_RANGE  0x43
#define BMI160_REG_CMD        0x7E

#define BMI160_CMD_ACC_NORMAL 0x11
#define BMI160_CMD_GYR_NORMAL 0x15
#define BMI160_CMD_SOFT_RESET 0xB6

uint8_t bmiAddr = BMI160_ADDR_1;
bool imuOk = false;

float gyroZRawDps = 0.0f;
float gyroZBiasDps = 0.0f;
float gyroZDps = 0.0f;
float yawDeg = 0.0f;
float yawTargetDeg = 0.0f;
float yawErrorDeg = 0.0f;

bool yawHoldEnabled = true;

float yawKp = 2.0f;       // output rad/s per rad
float yawKi = 0.0f;
float yawKd = 0.08f;
float yawIntegral = 0.0f;
float yawPrevErrorRad = 0.0f;
float yawIntegralLimit = 0.50f;

float MAX_YAW_W = 0.35f;       // rad/s
float YAW_TOLERANCE_DEG = 2.0f;
float YAW_RATE_STOP_EPS_DPS = 3.0f;

float YAW_SIGN = 1.0f;

// BMI160 gyro range ±250 dps gives 131.2 LSB/(deg/s)
const float BMI160_GYRO_LSB_PER_DPS = 131.2f;

// ============================================================
// Wheel Trims
// ============================================================

float FL_TRIM = 1.00f;
float FR_TRIM = 1.00f;
float RL_TRIM = 1.00f;
float RR_TRIM = 1.00f;

// ============================================================
// Position Loop Settings
// ============================================================

bool positionMode = false;
bool yawMode = false;
bool holdStopped = false;

float x_m = 0.0f;
float xTarget_m = 0.0f;
float posError_m = 0.0f;

float posKp = 0.75f;
float posKi = 0.00f;
float posKd = 0.08f;

float posIntegral = 0.0f;
float posPrevError = 0.0f;
float posIntegralLimit = 1.00f;

float MAX_POS_VX = 0.10f;

float POS_TOLERANCE_M = 0.020f;
float HOLD_REACTIVATE_M = 0.040f;
float VX_STOP_EPS = 0.015f;

float estimatedVx = 0.0f;

float ODOM_X_SCALE = 0.9907f;
bool USE_RL_IN_ODOM = false;

// ============================================================
// Pin Mapping
// ============================================================

// Front Left
#define FL_PWM   18
#define FL_DIR1  5
#define FL_DIR2  17
#define FL_ENC_A 34
#define FL_ENC_B 35

// Front Right
#define FR_PWM   19
#define FR_DIR1  33
#define FR_DIR2  32
#define FR_ENC_A 39
#define FR_ENC_B 36

// Rear Left
#define RL_PWM   13
#define RL_DIR1  15
#define RL_DIR2  23
#define RL_ENC_A 14
#define RL_ENC_B 27

// Rear Right
#define RR_PWM   4
#define RR_DIR1  16
#define RR_DIR2  2
#define RR_ENC_A 26
#define RR_ENC_B 25

// ============================================================
// RTOS
// ============================================================

SemaphoreHandle_t stateMutex;

// ============================================================`r`n// Encoder Counts
// ============================================================

volatile long enc_fl = 0;
volatile long enc_fr = 0;
volatile long enc_rl = 0;
volatile long enc_rr = 0;

long odomLastFL = 0;
long odomLastFR = 0;
long odomLastRL = 0;
long odomLastRR = 0;

// ============================================================
// Body Command
// ============================================================

float cmd_vx = 0.0f;
float cmd_vy = 0.0f;
float cmd_w  = 0.0f;

// ============================================================
// Wheel Controller Struct
// ============================================================

struct WheelController {
  const char* name;

  int pwmPin;
  int dir1;
  int dir2;

  volatile long* encCount;
  long lastCount;

  float targetRadS;
  float rawRadS;
  float filteredRadS;

  float integral;
  float prevError;

  float kpPos;
  float kiPos;
  float kdPos;
  float staticPos;
  float minPos;

  float kpNeg;
  float kiNeg;
  float kdNeg;
  float staticNeg;
  float minNeg;

  float integralLimit;

  float outputPWM;
  float lastAppliedPWM;

  int startupSamples;
};

// ============================================================
// Wheel Tuning
// ============================================================

WheelController FL = {
  "FL", FL_PWM, FL_DIR1, FL_DIR2, &enc_fl, 0,
  0, 0, 0, 0, 0,
  45.0f, 2.5f, 0.0f, 35.0f, 20.0f,
  60.0f, 5.0f, 0.0f, 20.0f, 12.0f,
  10.0f, 0, 0, 0
};

WheelController FR = {
  "FR", FR_PWM, FR_DIR1, FR_DIR2, &enc_fr, 0,
  0, 0, 0, 0, 0,
  55.0f, 8.0f, 0.0f, 45.0f, 35.0f,
  40.0f, 3.0f, 0.0f, 27.0f, 15.0f,
  10.0f, 0, 0, 0
};

WheelController RL = {
  "RL", RL_PWM, RL_DIR1, RL_DIR2, &enc_rl, 0,
  0, 0, 0, 0, 0,
  45.0f, 2.5f, 0.0f, 30.0f, 18.0f,
  70.0f, 5.0f, 0.0f, 25.0f, 15.0f,
  10.0f, 0, 0, 0
};

WheelController RR = {
  "RR", RR_PWM, RR_DIR1, RR_DIR2, &enc_rr, 0,
  0, 0, 0, 0, 0,
  75.0f, 5.5f, 0.0f, 35.0f, 20.0f,
  70.0f, 5.0f, 0.0f, 25.0f, 15.0f,
  10.0f, 0, 0, 0
};

// ============================================================
// Function Prototypes
// ============================================================

void startPositionMove(float distance_m);
void startPositionYawMove(float distance_m, float finalYawDeg);
void startYawMoveRelative(float deltaYawDeg);
void startYawMoveAbsolute(float targetYawDeg);
void startVelocityMove(float vx);
void stopRobot();
void resetAll();
void printStatus();
void computeWheelTargetsFromBody();
void zeroYaw();
void calibrateIMU(uint16_t samples);
bool calibrateOdometryWithDisplayed(float displayedDistance_m, float realDistance_m);
bool calibrateOdometryUsingCurrentX(float realDistance_m);
void resetOdometryOnly();

// ============================================================
// Utility
// ============================================================

float wrapDeg(float a) {
  while (a > 180.0f) a -= 360.0f;
  while (a < -180.0f) a += 360.0f;
  return a;
}

float degToRad(float d) {
  return d * PI / 180.0f;
}

float radToDeg(float r) {
  return r * 180.0f / PI;
}

// ============================================================
// BMI160 Low-Level I2C
// ============================================================

bool i2cWrite8(uint8_t addr, uint8_t reg, uint8_t value) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool i2cReadBytes(uint8_t addr, uint8_t reg, uint8_t* data, uint8_t len) {
  Wire.beginTransmission(addr);
  Wire.write(reg);

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  uint8_t received = Wire.requestFrom(addr, len);

  if (received != len) {
    return false;
  }

  for (uint8_t i = 0; i < len; i++) {
    data[i] = Wire.read();
  }

  return true;
}

uint8_t i2cRead8(uint8_t addr, uint8_t reg) {
  uint8_t value = 0xFF;
  i2cReadBytes(addr, reg, &value, 1);
  return value;
}

bool bmi160Detect() {
  uint8_t id1 = i2cRead8(BMI160_ADDR_1, BMI160_REG_CHIP_ID);
  uint8_t id2 = i2cRead8(BMI160_ADDR_2, BMI160_REG_CHIP_ID);

  if (id1 == 0xD1) {
    bmiAddr = BMI160_ADDR_1;
    return true;
  }

  if (id2 == 0xD1) {
    bmiAddr = BMI160_ADDR_2;
    return true;
  }

  return false;
}

bool bmi160Init() {
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  Wire.setClock(400000);

  delay(100);

  if (!bmi160Detect()) {
    Serial.println("BMI160 not detected at 0x68 or 0x69.");
    return false;
  }

  Serial.print("BMI160 detected at 0x");
  Serial.println(bmiAddr, HEX);

  i2cWrite8(bmiAddr, BMI160_REG_CMD, BMI160_CMD_SOFT_RESET);
  delay(100);

  if (!bmi160Detect()) {
    Serial.println("BMI160 disappeared after reset.");
    return false;
  }

  // Accel normal mode
  i2cWrite8(bmiAddr, BMI160_REG_CMD, BMI160_CMD_ACC_NORMAL);
  delay(50);

  // Gyro normal mode
  i2cWrite8(bmiAddr, BMI160_REG_CMD, BMI160_CMD_GYR_NORMAL);
  delay(100);

  // Accelerometer range ±2g
  i2cWrite8(bmiAddr, BMI160_REG_ACC_RANGE, 0x03);
  delay(10);

  // Gyroscope range ±250 deg/s
  i2cWrite8(bmiAddr, BMI160_REG_GYR_RANGE, 0x03);
  delay(10);

  uint8_t pmu = i2cRead8(bmiAddr, BMI160_REG_PMU_STATUS);

  Serial.print("BMI160 PMU_STATUS: 0x");
  Serial.println(pmu, HEX);

  return true;
}

bool bmi160ReadGyro(float &gxDps, float &gyDps, float &gzDps) {
  uint8_t data[6];

  if (!i2cReadBytes(bmiAddr, BMI160_REG_GYR_X_LSB, data, 6)) {
    return false;
  }

  int16_t rawX = (int16_t)((data[1] << 8) | data[0]);
  int16_t rawY = (int16_t)((data[3] << 8) | data[2]);
  int16_t rawZ = (int16_t)((data[5] << 8) | data[4]);

  gxDps = (float)rawX / BMI160_GYRO_LSB_PER_DPS;
  gyDps = (float)rawY / BMI160_GYRO_LSB_PER_DPS;
  gzDps = (float)rawZ / BMI160_GYRO_LSB_PER_DPS;

  return true;
}

void zeroYaw() {
  xSemaphoreTake(stateMutex, portMAX_DELAY);

  yawDeg = 0.0f;
  yawTargetDeg = 0.0f;
  yawErrorDeg = 0.0f;
  yawIntegral = 0.0f;
  yawPrevErrorRad = 0.0f;

  xSemaphoreGive(stateMutex);

  Serial.println("Yaw zeroed. Current orientation is now 0 deg.");
}

void calibrateIMU(uint16_t samples) {
  Serial.println();
  Serial.println("======================================");
  Serial.println("IMU calibration started.");
  Serial.println("Keep robot completely still.");
  Serial.println("Do not touch it.");
  Serial.println("======================================");

  stopAllMotors();
  delay(500);

  if (!imuOk) {
    Serial.println("Cannot calibrate: IMU not detected.");
    return;
  }

  float sumZ = 0.0f;
  uint16_t good = 0;

  for (uint16_t i = 0; i < samples; i++) {
    float gx, gy, gz;

    if (bmi160ReadGyro(gx, gy, gz)) {
      sumZ += gz;
      good++;
    }

    delay(5);
  }

  if (good < samples / 2) {
    Serial.println("IMU calibration failed: too many bad reads.");
    return;
  }

  xSemaphoreTake(stateMutex, portMAX_DELAY);

  gyroZBiasDps = sumZ / (float)good;
  yawDeg = 0.0f;
  yawTargetDeg = 0.0f;
  yawErrorDeg = 0.0f;
  yawIntegral = 0.0f;
  yawPrevErrorRad = 0.0f;

  xSemaphoreGive(stateMutex);

  Serial.print("IMU calibration done. Samples: ");
  Serial.print(good);
  Serial.print(" | gyroZBiasDps: ");
  Serial.println(gyroZBiasDps, 6);
  Serial.println("Yaw zeroed.");
}

// ============================================================
// Encoder ISRs
// ============================================================

void IRAM_ATTR isr_fl() {
  if (digitalRead(FL_ENC_B)) enc_fl--;
  else enc_fl++;
}

void IRAM_ATTR isr_fr() {
  if (digitalRead(FR_ENC_B)) enc_fr--;
  else enc_fr++;
}

void IRAM_ATTR isr_rl() {
  if (digitalRead(RL_ENC_B)) enc_rl++;
  else enc_rl--;
}

void IRAM_ATTR isr_rr() {
  if (digitalRead(RR_ENC_B)) enc_rr++;
  else enc_rr--;
}

// ============================================================
// Motor Output
// ============================================================

void setMotorPWMRaw(WheelController &w, float pwm) {
  pwm = constrain(pwm, -PWM_MAX, PWM_MAX);

  if (pwm > 0.0f) {
    digitalWrite(w.dir1, HIGH);
    digitalWrite(w.dir2, LOW);
    ledcWrite(w.pwmPin, (uint32_t)pwm);
  } 
  else if (pwm < 0.0f) {
    digitalWrite(w.dir1, LOW);
    digitalWrite(w.dir2, HIGH);
    ledcWrite(w.pwmPin, (uint32_t)(-pwm));
  } 
  else {
    digitalWrite(w.dir1, LOW);
    digitalWrite(w.dir2, LOW);
    ledcWrite(w.pwmPin, 0);
  }
}

float applySlewLimit(WheelController &w, float requestedPWM) {
  float delta = requestedPWM - w.lastAppliedPWM;
  delta = constrain(delta, -MAX_PWM_STEP, MAX_PWM_STEP);

  float limitedPWM = w.lastAppliedPWM + delta;
  w.lastAppliedPWM = limitedPWM;

  return limitedPWM;
}

void setMotorPWM(WheelController &w, float pwm) {
  pwm = constrain(pwm, -GROUND_PWM_LIMIT, GROUND_PWM_LIMIT);
  pwm = applySlewLimit(w, pwm);
  setMotorPWMRaw(w, pwm);
}

void stopAllMotors() {
  FL.lastAppliedPWM = 0;
  FR.lastAppliedPWM = 0;
  RL.lastAppliedPWM = 0;
  RR.lastAppliedPWM = 0;

  setMotorPWMRaw(FL, 0);
  setMotorPWMRaw(FR, 0);
  setMotorPWMRaw(RL, 0);
  setMotorPWMRaw(RR, 0);
}

// ============================================================
// Reset Helpers
// ============================================================

void resetWheelPID(WheelController &w) {
  w.integral = 0.0f;
  w.prevError = 0.0f;
  w.filteredRadS = 0.0f;
  w.rawRadS = 0.0f;
  w.outputPWM = 0.0f;
  w.lastAppliedPWM = 0.0f;
  w.startupSamples = 0;

  noInterrupts();
  w.lastCount = *(w.encCount);
  interrupts();
}

void resetAllWheelPID() {
  resetWheelPID(FL);
  resetWheelPID(FR);
  resetWheelPID(RL);
  resetWheelPID(RR);
}

void resetPositionPID() {
  posIntegral = 0.0f;
  posPrevError = 0.0f;
  posError_m = 0.0f;
}

void resetYawPID() {
  yawIntegral = 0.0f;
  yawPrevErrorRad = 0.0f;
}

void resetOdometry() {
  noInterrupts();
  odomLastFL = enc_fl;
  odomLastFR = enc_fr;
  odomLastRL = enc_rl;
  odomLastRR = enc_rr;
  interrupts();

  x_m = 0.0f;
  estimatedVx = 0.0f;
}

void resetAll() {
  xSemaphoreTake(stateMutex, portMAX_DELAY);

  cmd_vx = 0.0f;
  cmd_vy = 0.0f;
  cmd_w = 0.0f;

  FL.targetRadS = 0.0f;
  FR.targetRadS = 0.0f;
  RL.targetRadS = 0.0f;
  RR.targetRadS = 0.0f;

  positionMode = false;
  yawMode = false;
  holdStopped = false;

  resetAllWheelPID();
  resetPositionPID();
  resetYawPID();
  resetOdometry();

  yawDeg = 0.0f;
  yawTargetDeg = 0.0f;
  yawErrorDeg = 0.0f;

  xSemaphoreGive(stateMutex);

  stopAllMotors();
}


// ============================================================
// Odometry Calibration Helpers
// ============================================================

bool calibrateOdometryWithDisplayed(float displayedDistance_m, float realDistance_m) {
  displayedDistance_m = fabsf(displayedDistance_m);
  realDistance_m = fabsf(realDistance_m);

  if (displayedDistance_m <= 0.001f || realDistance_m <= 0.001f) {
    Serial.println("Odometry calibration failed: displayed or real distance is too small.");
    return false;
  }

  xSemaphoreTake(stateMutex, portMAX_DELAY);

  float oldScale = ODOM_X_SCALE;
  float ratio = realDistance_m / displayedDistance_m;
  ODOM_X_SCALE = constrain(oldScale * ratio, 0.001f, 5.0f);

  resetPositionPID();
  resetAllWheelPID();

  xSemaphoreGive(stateMutex);

  stopAllMotors();

  Serial.println();
  Serial.println("========== ODOMETRY CALIBRATION ==========");
  Serial.print("Old scale: ");
  Serial.println(oldScale, 6);
  Serial.print("Displayed distance: ");
  Serial.print(displayedDistance_m, 4);
  Serial.println(" m");
  Serial.print("Real measured distance: ");
  Serial.print(realDistance_m, 4);
  Serial.println(" m");
  Serial.print("Correction ratio real/displayed: ");
  Serial.println(ratio, 6);
  Serial.print("New ODOM_X_SCALE: ");
  Serial.println(ODOM_X_SCALE, 6);
  Serial.println("Now run: odomreset");
  Serial.println("Then test: pos 1.00");
  Serial.println("==========================================");
  Serial.println();

  return true;
}

bool calibrateOdometryUsingCurrentX(float realDistance_m) {
  float displayedDistance_m;

  xSemaphoreTake(stateMutex, portMAX_DELAY);
  displayedDistance_m = fabsf(x_m);
  xSemaphoreGive(stateMutex);

  return calibrateOdometryWithDisplayed(displayedDistance_m, realDistance_m);
}

void resetOdometryOnly() {
  xSemaphoreTake(stateMutex, portMAX_DELAY);

  resetOdometry();
  resetPositionPID();
  holdStopped = false;

  xSemaphoreGive(stateMutex);

  Serial.println("Odometry x reset to 0.000 m.");
}

// ============================================================
// PID Helpers
// ============================================================

void getActiveParams(
  WheelController &w,
  float setpoint,
  float &kp,
  float &ki,
  float &kd,
  float &staticPWM,
  float &minPWM
) {
  if (setpoint >= 0.0f) {
    kp = w.kpPos;
    ki = w.kiPos;
    kd = w.kdPos;
    staticPWM = w.staticPos;
    minPWM = w.minPos;
  } else {
    kp = w.kpNeg;
    ki = w.kiNeg;
    kd = w.kdNeg;
    staticPWM = w.staticNeg;
    minPWM = w.minNeg;
  }
}

float applyVelocityOutput(float pidPWM, float setpoint, float staticPWM, float minPWM) {
  if (fabsf(setpoint) < ZERO_SPEED_EPS) {
    return 0.0f;
  }

  const float direction = (setpoint > 0.0f) ? 1.0f : -1.0f;
  float finalPWM = direction * staticPWM + pidPWM;

  if (setpoint > 0.0f && finalPWM < 0.0f) finalPWM = 0.0f;
  if (setpoint < 0.0f && finalPWM > 0.0f) finalPWM = 0.0f;

  if (setpoint > 0.0f && finalPWM > 0.0f && finalPWM < minPWM) finalPWM = minPWM;
  if (setpoint < 0.0f && finalPWM < 0.0f && finalPWM > -minPWM) finalPWM = -minPWM;

  return constrain(finalPWM, -PWM_MAX, PWM_MAX);
}

// ============================================================
// Velocity Control
// ============================================================

void computeWheelTargetsFromBody() {
  float vx = cmd_vx;
  float vy = cmd_vy;
  float wz = cmd_w;

  float baseFL = (vx - vy - K_M * wz) / WHEEL_RADIUS_M;
  float baseFR = (vx + vy + K_M * wz) / WHEEL_RADIUS_M;
  float baseRL = (vx + vy - K_M * wz) / WHEEL_RADIUS_M;
  float baseRR = (vx - vy + K_M * wz) / WHEEL_RADIUS_M;

  FL.targetRadS = baseFL * FL_TRIM;
  FR.targetRadS = baseFR * FR_TRIM;
  RL.targetRadS = baseRL * RL_TRIM;
  RR.targetRadS = baseRR * RR_TRIM;
}

bool isOppositeLargeSpike(WheelController &w, float raw) {
  if (fabsf(w.targetRadS) < ZERO_SPEED_EPS) return false;

  bool oppositeSign = (w.targetRadS > 0.0f && raw < 0.0f) ||
                      (w.targetRadS < 0.0f && raw > 0.0f);

  return oppositeSign && fabsf(raw) > OPPOSITE_SIGN_REJECT_RAD_S;
}

void updateWheelVelocityPID(WheelController &w) {
  long count;

  noInterrupts();
  count = *(w.encCount);
  interrupts();

  const long delta = count - w.lastCount;
  w.lastCount = count;

  float raw = ((float)delta / ENCODER_PPR) * 2.0f * PI / CONTROL_DT_S;

  if (fabsf(raw) > MAX_VALID_RAD_S || isOppositeLargeSpike(w, raw)) {
    raw = w.filteredRadS;
  }
  else if (w.startupSamples < 5) {
    w.startupSamples++;
  }
  else {
    bool rawNearZero = fabsf(raw) < RAW_ZERO_EPS;

    if (!rawNearZero && fabsf(raw - w.filteredRadS) > MAX_JUMP_RAD_S) {
      raw = w.filteredRadS;
    }
  }

  w.rawRadS = raw;
  w.filteredRadS = alpha * raw + (1.0f - alpha) * w.filteredRadS;

  float kp, ki, kd, staticPWM, minPWM;
  getActiveParams(w, w.targetRadS, kp, ki, kd, staticPWM, minPWM);

  const float error = w.targetRadS - w.filteredRadS;

  w.integral += error * CONTROL_DT_S;
  w.integral = constrain(w.integral, -w.integralLimit, w.integralLimit);

  const float derivative = (error - w.prevError) / CONTROL_DT_S;
  w.prevError = error;

  const float pidPWM = kp * error + ki * w.integral + kd * derivative;
  w.outputPWM = applyVelocityOutput(pidPWM, w.targetRadS, staticPWM, minPWM);

  setMotorPWM(w, w.outputPWM);
}

// ============================================================
// Odometry + Yaw + Position Loop
// ============================================================

void updateOdometry() {
  long cfl, cfr, crl, crr;

  noInterrupts();
  cfl = enc_fl;
  cfr = enc_fr;
  crl = enc_rl;
  crr = enc_rr;
  interrupts();

  long dFL = cfl - odomLastFL;
  long dFR = cfr - odomLastFR;
  long dRL = crl - odomLastRL;
  long dRR = crr - odomLastRR;

  odomLastFL = cfl;
  odomLastFR = cfr;
  odomLastRL = crl;
  odomLastRR = crr;

  float radFL = ((float)dFL / ENCODER_PPR) * 2.0f * PI;
  float radFR = ((float)dFR / ENCODER_PPR) * 2.0f * PI;
  float radRL = ((float)dRL / ENCODER_PPR) * 2.0f * PI;
  float radRR = ((float)dRR / ENCODER_PPR) * 2.0f * PI;

  float dxRaw;

  if (USE_RL_IN_ODOM) {
    dxRaw = (WHEEL_RADIUS_M / 4.0f) * (radFL + radFR + radRL + radRR);
  } else {
    dxRaw = (WHEEL_RADIUS_M / 3.0f) * (radFL + radFR + radRR);
  }

  float dx = ODOM_X_SCALE * dxRaw;

  x_m += dx;
  estimatedVx = dx / CONTROL_DT_S;
}

float computeYawCorrectionW() {
  if (!yawHoldEnabled || !imuOk) {
    yawErrorDeg = 0.0f;
    yawIntegral = 0.0f;
    yawPrevErrorRad = 0.0f;
    return 0.0f;
  }

  yawErrorDeg = wrapDeg(yawTargetDeg - yawDeg);
  float errorRad = degToRad(yawErrorDeg);

  yawIntegral += errorRad * CONTROL_DT_S;
  yawIntegral = constrain(yawIntegral, -yawIntegralLimit, yawIntegralLimit);

  float derivative = (errorRad - yawPrevErrorRad) / CONTROL_DT_S;
  yawPrevErrorRad = errorRad;

  float wOut = yawKp * errorRad + yawKi * yawIntegral + yawKd * derivative;

  wOut = constrain(wOut, -MAX_YAW_W, MAX_YAW_W);

  return YAW_SIGN * wOut;
}

void updateYawOnlyLoop() {
  if (!yawMode) return;

  float yawAbsError = fabsf(wrapDeg(yawTargetDeg - yawDeg));
  bool yawInHold = yawAbsError < YAW_TOLERANCE_DEG && fabsf(gyroZDps) < YAW_RATE_STOP_EPS_DPS;

  if (yawInHold) {
    cmd_vx = 0.0f;
    cmd_vy = 0.0f;
    cmd_w = 0.0f;
    computeWheelTargetsFromBody();

    if (!holdStopped) {
      resetAllWheelPID();
      stopAllMotors();
      holdStopped = true;
      Serial.println("Yaw target reached. Holding angle.");
    }

    return;
  }

  holdStopped = false;

  cmd_vx = 0.0f;
  cmd_vy = 0.0f;
  cmd_w = computeYawCorrectionW();

  computeWheelTargetsFromBody();
}

void updatePositionLoop() {
  if (!positionMode) {
    updateYawOnlyLoop();
    return;
  }

  posError_m = xTarget_m - x_m;

  float yawAbsError = fabsf(wrapDeg(yawTargetDeg - yawDeg));
  bool xInHold = fabsf(posError_m) < POS_TOLERANCE_M && fabsf(estimatedVx) < VX_STOP_EPS;
  bool yawInHold = yawAbsError < YAW_TOLERANCE_DEG && fabsf(gyroZDps) < YAW_RATE_STOP_EPS_DPS;

  if (xInHold && yawInHold) {
    cmd_vx = 0.0f;
    cmd_vy = 0.0f;
    cmd_w = 0.0f;

    computeWheelTargetsFromBody();

    if (!holdStopped) {
      resetAllWheelPID();
      stopAllMotors();
      holdStopped = true;
      Serial.println("Position + yaw reached. Active hold enabled.");
    }

    return;
  }

  if (fabsf(posError_m) > HOLD_REACTIVATE_M || yawAbsError > YAW_TOLERANCE_DEG) {
    holdStopped = false;
  }

  posIntegral += posError_m * CONTROL_DT_S;
  posIntegral = constrain(posIntegral, -posIntegralLimit, posIntegralLimit);

  float derivative = (posError_m - posPrevError) / CONTROL_DT_S;
  posPrevError = posError_m;

  float vxOut = posKp * posError_m + posKi * posIntegral + posKd * derivative;
  vxOut = constrain(vxOut, -MAX_POS_VX, MAX_POS_VX);

  float wOut = computeYawCorrectionW();

  cmd_vx = vxOut;
  cmd_vy = 0.0f;
  cmd_w = wOut;

  computeWheelTargetsFromBody();
}

// ============================================================
// Commands
// ============================================================

void startPositionMove(float distance_m) {
  startPositionYawMove(distance_m, 0.0f);
}

void startPositionYawMove(float distance_m, float finalYawDeg) {
  xSemaphoreTake(stateMutex, portMAX_DELAY);

  resetOdometry();
  resetPositionPID();
  resetYawPID();
  resetAllWheelPID();

  xTarget_m = distance_m;
  positionMode = true;
  yawMode = false;
  holdStopped = false;

  // Relative mission yaw: current robot heading becomes 0, then target is finalYawDeg.
  yawDeg = 0.0f;
  yawTargetDeg = wrapDeg(finalYawDeg);
  yawErrorDeg = wrapDeg(yawTargetDeg - yawDeg);
  yawHoldEnabled = true;

  xSemaphoreGive(stateMutex);

  Serial.print("Starting position + yaw move: x = ");
  Serial.print(distance_m, 3);
  Serial.print(" m | final yaw target = ");
  Serial.print(finalYawDeg, 2);
  Serial.println(" deg");
}

void startYawMoveRelative(float deltaYawDeg) {
  xSemaphoreTake(stateMutex, portMAX_DELAY);

  positionMode = false;
  yawMode = true;
  holdStopped = false;

  resetYawPID();
  resetAllWheelPID();

  cmd_vx = 0.0f;
  cmd_vy = 0.0f;
  cmd_w = 0.0f;

  yawTargetDeg = wrapDeg(yawDeg + deltaYawDeg);
  yawErrorDeg = wrapDeg(yawTargetDeg - yawDeg);
  yawHoldEnabled = true;

  computeWheelTargetsFromBody();

  xSemaphoreGive(stateMutex);

  Serial.print("Starting relative yaw move: rotate by ");
  Serial.print(deltaYawDeg, 2);
  Serial.print(" deg | target = ");
  Serial.print(yawTargetDeg, 2);
  Serial.println(" deg");
}

void startYawMoveAbsolute(float targetYawDeg) {
  xSemaphoreTake(stateMutex, portMAX_DELAY);

  positionMode = false;
  yawMode = true;
  holdStopped = false;

  resetYawPID();
  resetAllWheelPID();

  cmd_vx = 0.0f;
  cmd_vy = 0.0f;
  cmd_w = 0.0f;

  yawTargetDeg = wrapDeg(targetYawDeg);
  yawErrorDeg = wrapDeg(yawTargetDeg - yawDeg);
  yawHoldEnabled = true;

  computeWheelTargetsFromBody();

  xSemaphoreGive(stateMutex);

  Serial.print("Starting absolute yaw move: target = ");
  Serial.print(yawTargetDeg, 2);
  Serial.println(" deg");
}

void startVelocityMove(float vx) {
  xSemaphoreTake(stateMutex, portMAX_DELAY);

  positionMode = false;
  yawMode = false;
  holdStopped = false;
  resetAllWheelPID();

  cmd_vx = constrain(vx, -0.50f, 0.50f);
  cmd_vy = 0.0f;
  cmd_w = 0.0f;

  computeWheelTargetsFromBody();

  xSemaphoreGive(stateMutex);

  Serial.print("Starting velocity move vx = ");
  Serial.println(cmd_vx, 3);
}

void stopRobot() {
  xSemaphoreTake(stateMutex, portMAX_DELAY);

  positionMode = false;
  yawMode = false;
  holdStopped = false;

  cmd_vx = 0.0f;
  cmd_vy = 0.0f;
  cmd_w = 0.0f;

  FL.targetRadS = 0.0f;
  FR.targetRadS = 0.0f;
  RL.targetRadS = 0.0f;
  RR.targetRadS = 0.0f;

  resetAllWheelPID();
  resetYawPID();

  xSemaphoreGive(stateMutex);

  stopAllMotors();
  Serial.println("Stopped.");
}

// ============================================================
// Serial Helpers
// ============================================================

void printHelp() {
  Serial.println();
  Serial.println("========== SERIAL COMMANDS ==========");
  Serial.println("Motion:");
  Serial.println("  pos 1.00        -> move forward 1 m and hold x + yaw=0");
  Serial.println("  pos -1.00       -> move backward 1 m and hold x + yaw=0");
  Serial.println("  yaw 45          -> rotate robot by +45 deg from current yaw");
  Serial.println("  yaw -45         -> rotate robot by -45 deg from current yaw");
  Serial.println("  yawabs 90       -> rotate to absolute yaw target 90 deg");
  Serial.println("  posyaw 1.00 45  -> move 1 m and finish at +45 deg yaw");
  Serial.println("  vel 0.08        -> direct forward velocity");
  Serial.println("  stop            -> stop");
  Serial.println("  reset           -> reset odometry, yaw and controllers");
  Serial.println("  show            -> print status");
  Serial.println();
  Serial.println("IMU / Yaw:");
  Serial.println("  imucal          -> calibrate gyro Z bias, robot still");
  Serial.println("  imucal 1500     -> calibrate with 1500 samples");
  Serial.println("  yawzero         -> set current yaw to 0");
  Serial.println("  imu             -> print IMU status");
  Serial.println("  yawhold 1       -> enable yaw hold");
  Serial.println("  yawhold 0       -> disable yaw hold");
  Serial.println("  yawkp 2.0");
  Serial.println("  yawki 0.0");
  Serial.println("  yawkd 0.08");
  Serial.println("  yawmax 0.35");
  Serial.println("  yawtol 2.0");
  Serial.println("  yawsign 1       -> normal yaw correction");
  Serial.println("  yawsign -1      -> reverse yaw correction");
  Serial.println();
  Serial.println("Position PID:");
  Serial.println("  kp 0.75");
  Serial.println("  ki 0.00");
  Serial.println("  kd 0.08");
  Serial.println("  maxvx 0.10");
  Serial.println("  tol 0.020");
  Serial.println("  react 0.040");
  Serial.println();
  Serial.println("Odometry:");
  Serial.println("  odom 0.9907        -> manually set odometry scale");
  Serial.println("  cal 0.53           -> use current displayed x and real distance");
  Serial.println("  cal2 1.011 0.53    -> displayed distance, real distance");
  Serial.println("  odomreset          -> reset x odometry only");
  Serial.println("  userl 0");
  Serial.println("  userl 1");
  Serial.println();
  Serial.println("Wheel Trims:");
  Serial.println("  trims 1.00 1.00 1.00 1.00");
  Serial.println("  trim fr 1.05");
  Serial.println("=====================================");
  Serial.println();
}

float wheelErrPct(WheelController &w) {
  if (fabsf(w.targetRadS) < 0.05f) return 0.0f;
  return 100.0f * (w.targetRadS - w.filteredRadS) / fabsf(w.targetRadS);
}

void printIMUStatus() {
  xSemaphoreTake(stateMutex, portMAX_DELAY);

  Serial.println("--------------- IMU STATUS ---------------");
  Serial.print("IMU OK: ");
  Serial.println(imuOk ? "YES" : "NO");

  Serial.print("BMI160 address: 0x");
  Serial.println(bmiAddr, HEX);

  Serial.print("gyroZRawDps: ");
  Serial.print(gyroZRawDps, 4);
  Serial.print(" | gyroZBiasDps: ");
  Serial.print(gyroZBiasDps, 4);
  Serial.print(" | gyroZDps corrected: ");
  Serial.println(gyroZDps, 4);

  Serial.print("yawDeg: ");
  Serial.print(yawDeg, 3);
  Serial.print(" | yawTargetDeg: ");
  Serial.print(yawTargetDeg, 3);
  Serial.print(" | yawErrorDeg: ");
  Serial.println(yawErrorDeg, 3);

  Serial.print("Yaw PID | Kp: ");
  Serial.print(yawKp, 3);
  Serial.print(" Ki: ");
  Serial.print(yawKi, 3);
  Serial.print(" Kd: ");
  Serial.print(yawKd, 3);
  Serial.print(" MaxW: ");
  Serial.print(MAX_YAW_W, 3);
  Serial.print(" TolDeg: ");
  Serial.print(YAW_TOLERANCE_DEG, 3);
  Serial.print(" Sign: ");
  Serial.println(YAW_SIGN, 1);

  xSemaphoreGive(stateMutex);
}

void printStatus() {
  long cfl, cfr, crl, crr;

  noInterrupts();
  cfl = enc_fl;
  cfr = enc_fr;
  crl = enc_rl;
  crr = enc_rr;
  interrupts();

  xSemaphoreTake(stateMutex, portMAX_DELAY);

  Serial.println("--------------------------------------------------");

  Serial.print("Mode: ");
  Serial.print(positionMode ? "POSITION + YAW HOLD" : (yawMode ? "YAW SETPOINT" : "VELOCITY/IDLE"));
  Serial.print(" | holdStopped: ");
  Serial.println(holdStopped ? "YES" : "NO");

  Serial.print("x: ");
  Serial.print(x_m, 3);
  Serial.print(" m | Target x: ");
  Serial.print(xTarget_m, 3);
  Serial.print(" m | Error: ");
  Serial.print(posError_m, 3);
  Serial.print(" m | est vx: ");
  Serial.println(estimatedVx, 3);

  Serial.print("Yaw: ");
  Serial.print(yawDeg, 2);
  Serial.print(" deg | Target: ");
  Serial.print(yawTargetDeg, 2);
  Serial.print(" deg | Error: ");
  Serial.print(yawErrorDeg, 2);
  Serial.print(" deg | Gz: ");
  Serial.print(gyroZDps, 2);
  Serial.println(" dps");

  Serial.print("CMD vx: ");
  Serial.print(cmd_vx, 3);
  Serial.print(" | vy: ");
  Serial.print(cmd_vy, 3);
  Serial.print(" | w: ");
  Serial.println(cmd_w, 3);

  Serial.print("Position PID | Kp: ");
  Serial.print(posKp, 3);
  Serial.print(" Ki: ");
  Serial.print(posKi, 3);
  Serial.print(" Kd: ");
  Serial.print(posKd, 3);
  Serial.print(" | Max vx: ");
  Serial.println(MAX_POS_VX, 3);

  Serial.print("Yaw PID | Kp: ");
  Serial.print(yawKp, 3);
  Serial.print(" Ki: ");
  Serial.print(yawKi, 3);
  Serial.print(" Kd: ");
  Serial.print(yawKd, 3);
  Serial.print(" | Max w: ");
  Serial.print(MAX_YAW_W, 3);
  Serial.print(" | Sign: ");
  Serial.println(YAW_SIGN, 1);

  Serial.print("Odom scale: ");
  Serial.print(ODOM_X_SCALE, 4);
  Serial.print(" | Use RL in odom: ");
  Serial.println(USE_RL_IN_ODOM ? "YES" : "NO");

  Serial.print("Trims | FL: ");
  Serial.print(FL_TRIM, 3);
  Serial.print(" FR: ");
  Serial.print(FR_TRIM, 3);
  Serial.print(" RL: ");
  Serial.print(RL_TRIM, 3);
  Serial.print(" RR: ");
  Serial.println(RR_TRIM, 3);

  Serial.print("Target rad/s | FL: ");
  Serial.print(FL.targetRadS, 2);
  Serial.print(" FR: ");
  Serial.print(FR.targetRadS, 2);
  Serial.print(" RL: ");
  Serial.print(RL.targetRadS, 2);
  Serial.print(" RR: ");
  Serial.println(RR.targetRadS, 2);

  Serial.print("Actual rad/s | FL: ");
  Serial.print(FL.filteredRadS, 2);
  Serial.print(" FR: ");
  Serial.print(FR.filteredRadS, 2);
  Serial.print(" RL: ");
  Serial.print(RL.filteredRadS, 2);
  Serial.print(" RR: ");
  Serial.println(RR.filteredRadS, 2);

  Serial.print("Error %      | FL: ");
  Serial.print(wheelErrPct(FL), 1);
  Serial.print(" FR: ");
  Serial.print(wheelErrPct(FR), 1);
  Serial.print(" RL: ");
  Serial.print(wheelErrPct(RL), 1);
  Serial.print(" RR: ");
  Serial.println(wheelErrPct(RR), 1);

  Serial.print("PWM applied  | FL: ");
  Serial.print(FL.lastAppliedPWM, 1);
  Serial.print(" FR: ");
  Serial.print(FR.lastAppliedPWM, 1);
  Serial.print(" RL: ");
  Serial.print(RL.lastAppliedPWM, 1);
  Serial.print(" RR: ");
  Serial.println(RR.lastAppliedPWM, 1);

  Serial.print("Counts       | FL: ");
  Serial.print(cfl);
  Serial.print(" FR: ");
  Serial.print(cfr);
  Serial.print(" RL: ");
  Serial.print(crl);
  Serial.print(" RR: ");
  Serial.println(crr);

  xSemaphoreGive(stateMutex);
}

// ============================================================
// Serial Parser
// ============================================================

String getWord(String s, int index) {
  s.trim();
  int currentIndex = 0;
  int start = 0;

  while (start < s.length()) {
    while (start < s.length() && s[start] == ' ') start++;

    int end = s.indexOf(' ', start);
    if (end == -1) end = s.length();

    if (currentIndex == index) {
      return s.substring(start, end);
    }

    currentIndex++;
    start = end + 1;
  }

  return "";
}

void handleLine(String line) {
  line.trim();
  line.toLowerCase();

  if (line.length() == 0) return;

  String cmd = getWord(line, 0);
  String a1 = getWord(line, 1);
  String a2 = getWord(line, 2);
  String a3 = getWord(line, 3);
  String a4 = getWord(line, 4);

  if (cmd == "pos") {
    float distance = constrain(a1.toFloat(), -5.0f, 5.0f);
    startPositionMove(distance);
  }

  else if (cmd == "posyaw") {
    float distance = constrain(a1.toFloat(), -5.0f, 5.0f);
    float finalYaw = constrain(a2.toFloat(), -180.0f, 180.0f);
    startPositionYawMove(distance, finalYaw);
  }

  else if (cmd == "yaw") {
    float deltaYaw = constrain(a1.toFloat(), -180.0f, 180.0f);
    startYawMoveRelative(deltaYaw);
  }

  else if (cmd == "yawabs") {
    float targetYaw = constrain(a1.toFloat(), -180.0f, 180.0f);
    startYawMoveAbsolute(targetYaw);
  }

  else if (cmd == "vel") {
    startVelocityMove(a1.toFloat());
  }

  else if (cmd == "kp") {
    xSemaphoreTake(stateMutex, portMAX_DELAY);
    posKp = constrain(a1.toFloat(), 0.0f, 20.0f);
    xSemaphoreGive(stateMutex);
  }

  else if (cmd == "ki") {
    xSemaphoreTake(stateMutex, portMAX_DELAY);
    posKi = constrain(a1.toFloat(), 0.0f, 10.0f);
    xSemaphoreGive(stateMutex);
  }

  else if (cmd == "kd") {
    xSemaphoreTake(stateMutex, portMAX_DELAY);
    posKd = constrain(a1.toFloat(), 0.0f, 10.0f);
    xSemaphoreGive(stateMutex);
  }

  else if (cmd == "maxvx") {
    xSemaphoreTake(stateMutex, portMAX_DELAY);
    MAX_POS_VX = constrain(a1.toFloat(), 0.01f, 0.50f);
    xSemaphoreGive(stateMutex);
  }

  else if (cmd == "tol") {
    xSemaphoreTake(stateMutex, portMAX_DELAY);
    POS_TOLERANCE_M = constrain(a1.toFloat(), 0.001f, 0.300f);
    xSemaphoreGive(stateMutex);
  }

  else if (cmd == "react") {
    xSemaphoreTake(stateMutex, portMAX_DELAY);
    HOLD_REACTIVATE_M = constrain(a1.toFloat(), POS_TOLERANCE_M + 0.001f, 0.500f);
    xSemaphoreGive(stateMutex);
  }

  else if (cmd == "odom") {
    xSemaphoreTake(stateMutex, portMAX_DELAY);
    ODOM_X_SCALE = constrain(a1.toFloat(), 0.01f, 5.0f);
    xSemaphoreGive(stateMutex);
  }

  else if (cmd == "cal") {
    // Uses the current displayed x_m value as the displayed distance.
    // Example after a test run where real distance was 0.53 m:
    //   cal 0.53
    float realDistance = a1.toFloat();
    calibrateOdometryUsingCurrentX(realDistance);
  }

  else if (cmd == "cal2") {
    // Safer manual calibration using both values directly.
    // Example from your test:
    //   cal2 1.011 0.53
    // Meaning: robot estimated 1.011 m, but actually moved 0.53 m.
    float displayedDistance = a1.toFloat();
    float realDistance = a2.toFloat();
    calibrateOdometryWithDisplayed(displayedDistance, realDistance);
  }

  else if (cmd == "odomreset") {
    resetOdometryOnly();
  }

  else if (cmd == "pwmcap") {
    xSemaphoreTake(stateMutex, portMAX_DELAY);
    GROUND_PWM_LIMIT = constrain(a1.toFloat(), 20.0f, 255.0f);
    xSemaphoreGive(stateMutex);
  }

  else if (cmd == "slew") {
    xSemaphoreTake(stateMutex, portMAX_DELAY);
    MAX_PWM_STEP = constrain(a1.toFloat(), 1.0f, 255.0f);
    xSemaphoreGive(stateMutex);
  }

  else if (cmd == "userl") {
    xSemaphoreTake(stateMutex, portMAX_DELAY);
    USE_RL_IN_ODOM = (a1.toInt() != 0);
    xSemaphoreGive(stateMutex);
  }

  else if (cmd == "trims") {
    xSemaphoreTake(stateMutex, portMAX_DELAY);
    FL_TRIM = constrain(a1.toFloat(), 0.50f, 1.80f);
    FR_TRIM = constrain(a2.toFloat(), 0.50f, 1.80f);
    RL_TRIM = constrain(a3.toFloat(), 0.50f, 1.80f);
    RR_TRIM = constrain(a4.toFloat(), 0.50f, 1.80f);
    computeWheelTargetsFromBody();
    xSemaphoreGive(stateMutex);
  }

  else if (cmd == "trim") {
    String wheel = a1;
    float value = constrain(a2.toFloat(), 0.50f, 1.80f);

    xSemaphoreTake(stateMutex, portMAX_DELAY);

    if (wheel == "fl") FL_TRIM = value;
    else if (wheel == "fr") FR_TRIM = value;
    else if (wheel == "rl") RL_TRIM = value;
    else if (wheel == "rr") RR_TRIM = value;
    else Serial.println("Unknown wheel. Use fl/fr/rl/rr.");

    computeWheelTargetsFromBody();

    xSemaphoreGive(stateMutex);
  }

  else if (cmd == "imucal") {
    uint16_t samples = a1.length() > 0 ? constrain(a1.toInt(), 200, 5000) : 1200;
    calibrateIMU(samples);
  }

  else if (cmd == "yawzero") {
    zeroYaw();
  }

  else if (cmd == "imu") {
    printIMUStatus();
  }

  else if (cmd == "yawhold") {
    xSemaphoreTake(stateMutex, portMAX_DELAY);
    yawHoldEnabled = (a1.toInt() != 0);
    resetYawPID();
    xSemaphoreGive(stateMutex);

    Serial.print("Yaw hold: ");
    Serial.println(yawHoldEnabled ? "ON" : "OFF");
  }

  else if (cmd == "yawkp") {
    xSemaphoreTake(stateMutex, portMAX_DELAY);
    yawKp = constrain(a1.toFloat(), 0.0f, 20.0f);
    xSemaphoreGive(stateMutex);
  }

  else if (cmd == "yawki") {
    xSemaphoreTake(stateMutex, portMAX_DELAY);
    yawKi = constrain(a1.toFloat(), 0.0f, 10.0f);
    xSemaphoreGive(stateMutex);
  }

  else if (cmd == "yawkd") {
    xSemaphoreTake(stateMutex, portMAX_DELAY);
    yawKd = constrain(a1.toFloat(), 0.0f, 10.0f);
    xSemaphoreGive(stateMutex);
  }

  else if (cmd == "yawmax") {
    xSemaphoreTake(stateMutex, portMAX_DELAY);
    MAX_YAW_W = constrain(a1.toFloat(), 0.05f, 2.0f);
    xSemaphoreGive(stateMutex);
  }

  else if (cmd == "yawtol") {
    xSemaphoreTake(stateMutex, portMAX_DELAY);
    YAW_TOLERANCE_DEG = constrain(a1.toFloat(), 0.2f, 20.0f);
    xSemaphoreGive(stateMutex);
  }

  else if (cmd == "yawsign") {
    xSemaphoreTake(stateMutex, portMAX_DELAY);
    YAW_SIGN = (a1.toFloat() < 0.0f) ? -1.0f : 1.0f;
    resetYawPID();
    xSemaphoreGive(stateMutex);
  }

  else if (cmd == "stop" || cmd == "0") {
    stopRobot();
  }

  else if (cmd == "reset") {
    resetAll();
    Serial.println("Reset complete.");
  }

  else if (cmd == "show") {
    printStatus();
  }

  else if (cmd == "help") {
    printHelp();
  }

  else {
    Serial.print("Unknown command: ");
    Serial.println(line);
    Serial.println("Type help.");
  }
}


// ============================================================`r`n// RTOS Tasks
// ============================================================

void controlTask(void *parameter) {
  TickType_t lastWakeTime = xTaskGetTickCount();
  const TickType_t period = pdMS_TO_TICKS(CONTROL_DT_MS);

  for (;;) {
    xSemaphoreTake(stateMutex, portMAX_DELAY);

    updateOdometry();
    updatePositionLoop();

    updateWheelVelocityPID(FL);
    updateWheelVelocityPID(FR);
    updateWheelVelocityPID(RL);
    updateWheelVelocityPID(RR);

    xSemaphoreGive(stateMutex);

    vTaskDelayUntil(&lastWakeTime, period);
  }
}

void imuTask(void *parameter) {
  uint32_t lastMicros = micros();

  for (;;) {
    if (imuOk) {
      float gx, gy, gz;

      if (bmi160ReadGyro(gx, gy, gz)) {
        uint32_t nowMicros = micros();
        float dt = (nowMicros - lastMicros) / 1000000.0f;
        lastMicros = nowMicros;

        if (dt > 0.0f && dt < 0.1f) {
          float correctedGz = gz - gyroZBiasDps;

          xSemaphoreTake(stateMutex, portMAX_DELAY);

          gyroZRawDps = gz;
          gyroZDps = correctedGz;
          yawDeg = wrapDeg(yawDeg + correctedGz * dt);
          yawErrorDeg = wrapDeg(yawTargetDeg - yawDeg);

          xSemaphoreGive(stateMutex);
        }
      }
    }

    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

void serialTask(void *parameter) {
  String line = "";

  for (;;) {
    while (Serial.available()) {
      char c = Serial.read();

      if (c == '\n') {
        handleLine(line);
        line = "";
      } else if (c != '\r') {
        line += c;
      }
    }

    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

void statusTask(void *parameter) {
  for (;;) {
    printStatus();
    vTaskDelay(pdMS_TO_TICKS(1500));
  }
}

// ============================================================`r`n// Setup
// ============================================================

void setupMotorPins(WheelController &w) {
  pinMode(w.dir1, OUTPUT);
  pinMode(w.dir2, OUTPUT);

  digitalWrite(w.dir1, LOW);
  digitalWrite(w.dir2, LOW);

  bool ok = ledcAttach(w.pwmPin, PWM_FREQ_HZ, PWM_RESOLUTION);

  if (!ok) {
    Serial.print("ERROR: LEDC attach failed for ");
    Serial.println(w.name);

    while (true) {
      delay(1000);
    }
  }

  setMotorPWMRaw(w, 0);
}

void setupEncoderPins() {
  pinMode(FL_ENC_A, INPUT);
  pinMode(FL_ENC_B, INPUT);

  pinMode(FR_ENC_A, INPUT);
  pinMode(FR_ENC_B, INPUT);

  pinMode(RL_ENC_A, INPUT_PULLUP);
  pinMode(RL_ENC_B, INPUT_PULLUP);

  pinMode(RR_ENC_A, INPUT_PULLUP);
  pinMode(RR_ENC_B, INPUT_PULLUP);

  attachInterrupt(digitalPinToInterrupt(FL_ENC_A), isr_fl, RISING);
  attachInterrupt(digitalPinToInterrupt(FR_ENC_A), isr_fr, RISING);
  attachInterrupt(digitalPinToInterrupt(RL_ENC_A), isr_rl, RISING);
  attachInterrupt(digitalPinToInterrupt(RR_ENC_A), isr_rr, RISING);
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  stateMutex = xSemaphoreCreateMutex();

  if (stateMutex == NULL) {
    Serial.println("ERROR: Failed to create mutex.");
    while (true) {
      delay(1000);
    }
  }

  setupMotorPins(FL);
  setupMotorPins(FR);
  setupMotorPins(RL);
  setupMotorPins(RR);

  setupEncoderPins();

  resetAll();

  imuOk = bmi160Init();

  if (imuOk) {
    Serial.println("BMI160 initialized.");
    Serial.println("Run imucal before ground testing.");
  } else {
    Serial.println("IMU failed. Position x control still works, yaw hold disabled.");
    yawHoldEnabled = false;
  }

  Serial.println("======================================");
  Serial.println("Raw RTOS PID Controller with BMI160 Yaw Hold");
  Serial.println("Use Serial Monitor, 115200 baud, Newline.");
  Serial.println("Type help for commands.");
  Serial.println("======================================");

  printHelp();

  xTaskCreatePinnedToCore(controlTask, "controlTask", 12000, NULL, 3, NULL, 1);
  xTaskCreatePinnedToCore(imuTask,     "imuTask",     7000,  NULL, 3, NULL, 1);
  xTaskCreatePinnedToCore(serialTask,  "serialTask",  7000,  NULL, 2, NULL, 0);
  xTaskCreatePinnedToCore(statusTask,  "statusTask",  8000,  NULL, 1, NULL, 0);
}

void loop() {
  vTaskDelay(pdMS_TO_TICKS(1000));
}
