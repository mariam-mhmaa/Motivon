#include <Arduino.h>
#include <esp_arduino_version.h>

constexpr uint32_t PWM_FREQ_HZ = 20000;
constexpr uint8_t PWM_RESOLUTION = 8;

// Same motor-driver pin mapping used by Motivon_ROS firmware.
#define FR_PWM 18
#define FR_DIR1 5
#define FR_DIR2 17

#define FL_PWM 19
#define FL_DIR1 33
#define FL_DIR2 32

#define RR_PWM 4
#define RR_DIR1 16
#define RR_DIR2 2

#define RL_PWM 13
#define RL_DIR1 15
#define RL_DIR2 23

constexpr int TEST_PWM = 180;
constexpr int RUN_MS = 3000;
constexpr int STOP_MS = 1000;

struct Motor {
  const char *name;
  int pwm_pin;
  int channel;
  int dir1_pin;
  int dir2_pin;
};

Motor front_right = {"FR", FR_PWM, 0, FR_DIR1, FR_DIR2};
Motor front_left = {"FL", FL_PWM, 1, FL_DIR1, FL_DIR2};
Motor rear_right = {"RR", RR_PWM, 2, RR_DIR1, RR_DIR2};
Motor rear_left = {"RL", RL_PWM, 3, RL_DIR1, RL_DIR2};

Motor *all_motors[] = {&front_left, &front_right, &rear_left, &rear_right};

void writePwm(const Motor &motor, int duty) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(motor.pwm_pin, duty);
#else
  ledcWrite(motor.channel, duty);
#endif
}

void setupMotor(const Motor &motor) {
  pinMode(motor.dir1_pin, OUTPUT);
  pinMode(motor.dir2_pin, OUTPUT);
  digitalWrite(motor.dir1_pin, LOW);
  digitalWrite(motor.dir2_pin, LOW);

#if ESP_ARDUINO_VERSION_MAJOR >= 3
  if (!ledcAttach(motor.pwm_pin, PWM_FREQ_HZ, PWM_RESOLUTION)) {
    Serial.printf("PWM attach failed for %s on pin %d\n", motor.name, motor.pwm_pin);
    while (true) {
      delay(1000);
    }
  }
#else
  if (ledcSetup(motor.channel, PWM_FREQ_HZ, PWM_RESOLUTION) <= 0.0) {
    Serial.printf("PWM setup failed for %s on channel %d\n", motor.name, motor.channel);
    while (true) {
      delay(1000);
    }
  }
  ledcAttachPin(motor.pwm_pin, motor.channel);
#endif
  writePwm(motor, 0);
}

void setMotor(const Motor &motor, int pwm) {
  pwm = constrain(pwm, -255, 255);
  if (pwm > 0) {
    digitalWrite(motor.dir1_pin, HIGH);
    digitalWrite(motor.dir2_pin, LOW);
    writePwm(motor, pwm);
  } else if (pwm < 0) {
    digitalWrite(motor.dir1_pin, LOW);
    digitalWrite(motor.dir2_pin, HIGH);
    writePwm(motor, -pwm);
  } else {
    digitalWrite(motor.dir1_pin, LOW);
    digitalWrite(motor.dir2_pin, LOW);
    writePwm(motor, 0);
  }
}

void stopAll() {
  for (Motor *motor : all_motors) {
    setMotor(*motor, 0);
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println();
  Serial.println("Motivon front-left standalone ESP motor test.");
  Serial.println("No ROS, no Wi-Fi, no sensors. Only front-left moves.");
  Serial.printf("TEST_PWM=%d, RUN_MS=%d, STOP_MS=%d\n", TEST_PWM, RUN_MS, STOP_MS);

  for (Motor *motor : all_motors) {
    setupMotor(*motor);
  }
  stopAll();
  delay(1500);
}

void loop() {
  Serial.println("Moving FRONT LEFT forward.");
  stopAll();
  delay(200);

  setMotor(front_left, TEST_PWM);
  setMotor(rear_right, 0);
  setMotor(front_right, 0);
  setMotor(rear_left, 0);

  delay(RUN_MS);

  Serial.println("Stopping all motors.");
  stopAll();
  delay(STOP_MS);
}
