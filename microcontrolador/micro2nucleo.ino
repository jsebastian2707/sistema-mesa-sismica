#include <Arduino.h> 
#include <FastAccelStepper.h>
#include <AS5600.h>
#include <Wire.h>

#define STEP_PIN 32
#define DIR_PIN 33 
#define ENABLE_PIN 25 

FastAccelStepperEngine engine;
FastAccelStepper *stepper = nullptr;
AS5600 encoder;
const int CPR = 4096;             // cuentas por vuelta del AS5600
const uint32_t SAMPLE_MS = 5;     // muestreo del encoder (ms)
int MAX_ACCEPTABLE_DELTA = 1500;  // umbral para rechazar spikes (ajustable)
volatile int32_t position_counts = 0;  // acumulador de delta en cuentas (puede ser negativo)
volatile int16_t last_raw = -1;

void readEncoderTask(void *param) {
  TickType_t lastWake = xTaskGetTickCount();
  int32_t countsCopy;
  for (;;) {
    vTaskDelayUntil(&lastWake, pdMS_TO_TICKS(SAMPLE_MS));
    int16_t raw = encoder.rawAngle();  // 0..4095
    if (last_raw < 0) {
      last_raw = raw;
      continue;
    }
    int delta = raw - last_raw;
    // unwrap  podria servir aumentar el valor
    if (delta > (CPR / 2)) delta -= CPR;
    else if (delta < -(CPR / 2)) delta += CPR;
    if (abs(delta) <= MAX_ACCEPTABLE_DELTA) {
      position_counts += delta;
    }
    countsCopy = position_counts;
    float absoluteDeg = (countsCopy * 360.0f) / (float)CPR;  // grados absolutos (puede ser >360)
    Serial.println(absoluteDeg);
    last_raw = raw;
  }
  //vTaskDelay(pdMS_TO_TICKS(5));  // cada 5 ms
}

void setup() {
  Serial.begin(230400);
  Wire.begin();
  Wire.setClock(400000);

  if (!encoder.isConnected()) {
    Serial.println("AS5600 no detectado. Revisa conexiones.");
    while (1) delay(1000);
  }
  engine.init();
  stepper = engine.stepperConnectToPin(STEP_PIN);
  if (stepper) {
    stepper->setDirectionPin(DIR_PIN);
    stepper->setEnablePin(ENABLE_PIN);
    stepper->setAutoEnable(true); 
    stepper->setSpeedInHz(200000);
    stepper->setAcceleration(180000);
  } else {
    Serial.println("Stepper motor initialization failed!");
    while (1);
  }
  Serial.println("Sistema inicializado. Listo para recibir comandos.");
  Serial.println("Comandos: m<pos>, s<vel>, a<acel>, e<0/1>");
  
  if (!encoder.detectMagnet()) {
    Serial.println("ADVERTENCIA: No se detecta iman");
  } else {
    uint16_t strength = encoder.readMagnitude();
    Serial.print("iman detectado. Intensidad: ");
    Serial.println(strength);
    if (strength < 300) {
      Serial.println("Imán muy débil - acércalo mas");
    } else if (strength > 800) {
      Serial.println("Imán muy fuerte - aléjalo un poco");
    } else {
      Serial.println("Intensidad óptima");
    }
  }
  xTaskCreatePinnedToCore(readEncoderTask, "EncTask", 4096, NULL, 2, NULL, 0);
}

void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    int data = command.substring(1).toInt();
    if (command.startsWith("m")) {
      stepper->moveTo(data);
    } else if (command.startsWith("s")) {
      stepper->setSpeedInHz(data);
    } else if (command.startsWith("a")) {
      stepper->setAcceleration(data);
    } 
  }
}