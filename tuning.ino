const int randPin = 27;

void setup() {
    Serial.begin(115200);
    pinMode(randPin, INPUT);
}

void loop() {

    int bit = digitalRead(randPin);

    Serial.println(bit);

    delayMicroseconds(100);
}
