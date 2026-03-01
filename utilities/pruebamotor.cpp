#include <FastAccelStepper.h>

// PINOUT (Asegúrate que coincidan con tu cableado físico)
#define STEP_PIN 32
#define DIR_PIN 33
#define ENABLE_PIN 25

FastAccelStepperEngine engine;
FastAccelStepper *stepper = NULL;

void setup() {
  Serial.begin(115200);
  Serial.println("Iniciando Test de Motor...");
  engine.init();
  stepper = engine.stepperConnectToPin(STEP_PIN);
  if (stepper) {
    stepper->setDirectionPin(DIR_PIN);
    stepper->setEnablePin(ENABLE_PIN);
    stepper->setAutoEnable(true);
    stepper->setSpeedInHz(201200);
    stepper->setAcceleration(280000);
    Serial.println("Motor OK");
  } else {
    Serial.println("ERROR: al inicializar el motor");
    while(1);
  }
  delay(100);
  Serial.print("getMaxSpeedInTicks-->");
  Serial.println(stepper->getMaxSpeedInTicks());
  Serial.print("getMaxSpeedInUs-->");
  Serial.println(stepper->getMaxSpeedInUs());
  Serial.print("TICKS_PER_S-->");
  Serial.println(TICKS_PER_S);
}

void loop() {
  stepper->moveTo(-200, true);
  stepper->moveTo(0, true);
  stepper->moveTo(-200, true);
  stepper->moveTo(0, true);
}