#include <SoftwareSerial.h>

const String PHONE_1 = "+919999999999";

#define rxPin 4
#define txPin 3
SoftwareSerial sim900A(rxPin, txPin);

#define flame_sensor_pin 2

boolean fire_flag = 0;

#define buzzer_pin 5

void setup()
{
  Serial.begin(115200);
  sim900A.begin(9600);

  pinMode(flame_sensor_pin, INPUT);
  pinMode(buzzer_pin, OUTPUT);
  digitalWrite(buzzer_pin, LOW);

  Serial.println("Initializing...");

  sim900A.println("AT");
  delay(1000);
  sim900A.println("AT+CMGF=1");
  delay(1000);
}

void loop()
{
  while (sim900A.available()) {
    Serial.println(sim900A.readString());
  }

  int flame_value = digitalRead(flame_sensor_pin);

  if (flame_value == LOW) {
    digitalWrite(buzzer_pin, HIGH);

    if (fire_flag == 0) {
      Serial.println("Fire Detected.");
      fire_flag = 1;
      send_multi_sms();
      make_multi_call();
    }

  } else {
    digitalWrite(buzzer_pin, LOW);
    fire_flag = 0;
  }
}

void send_multi_sms()
{
  if (PHONE_1 != "") {
    Serial.print("Phone 1: ");
    send_sms("Fire is Detected", PHONE_1);
  }
}

void make_multi_call()
{
  if (PHONE_1 != "") {
    Serial.print("Phone 1: ");
    make_call(PHONE_1);
  }
}

void send_sms(String text, String phone)
{
  Serial.println("Sending SMS...");
  delay(50);
  sim900A.print("AT+CMGF=1\r");
  delay(1000);
  sim900A.print("AT+CMGS=\"" + phone + "\"\r");
  delay(1000);
  sim900A.print(text);
  delay(100);
  sim900A.write(0x1A);
  delay(5000);
}

void make_call(String phone)
{
  Serial.println("Calling...");
  sim900A.println("ATD" + phone + ";");
  delay(20000);
  sim900A.println("ATH");
  delay(1000);
}
