/*
  Indoor Landmark Position Recovery — ESP32 BLE Beacon Advertiser & Scanner
  -------------------------------------------------------------------------
  Allows an ESP32 to either:
  1. ADVERTISER MODE: Broadcast as one of the 5 landmark beacons (B1, B2, B3, B4, B5)
  2. SCANNER MODE: Scan nearby BLE beacons and output RSSI readings formatted for the Python backend:
     {"B1": -62.0, "B2": -81.0}
*/

#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEScan.h>
#include <BLEAdvertisedDevice.h>

// Set to true to broadcast as a Landmark; false to scan for landmarks
#define MODE_ADVERTISER false

// If advertiser: which landmark ID to broadcast ("B1", "B2", "B3", "B4", or "B5")
const char* BEACON_LANDMARK_ID = "B3";

// Scanner configuration
int scanTime = 1; // In seconds
BLEScan* pBLEScan;

class MyAdvertisedDeviceCallbacks: public BLEAdvertisedDeviceCallbacks {
    void onResult(BLEAdvertisedDevice advertisedDevice) {
      String name = advertisedDevice.getName().c_str();
      if (name.startsWith("B") && name.length() <= 3) {
        int rssi = advertisedDevice.getRSSI();
        Serial.printf("{\"landmark\":\"%s\",\"rssi\":%d}\n", name.c_str(), rssi);
      }
    }
};

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("=========================================");
  Serial.println(" CampusEcho — BLE Landmark Utility");
  Serial.println("=========================================");

#if MODE_ADVERTISER
  Serial.printf("Starting BLE Advertiser for Landmark: %s\n", BEACON_LANDMARK_ID);
  BLEDevice::init(BEACON_LANDMARK_ID);
  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->setScanResponse(true);
  pAdvertising->setMinPreferred(0x06);
  pAdvertising->setMaxPreferred(0x12);
  BLEDevice::startAdvertising();
  Serial.println("Broadcasting BLE Landmark Beacon...");
#else
  Serial.println("Starting BLE Landmark Scanner...");
  BLEDevice::init("");
  pBLEScan = BLEDevice::getScan();
  pBLEScan->setAdvertisedDeviceCallbacks(new MyAdvertisedDeviceCallbacks());
  pBLEScan->setActiveScan(true);
  pBLEScan->setInterval(100);
  pBLEScan->setWindow(99);
#endif
}

void loop() {
#if !MODE_ADVERTISER
  BLEScanResults *foundDevices = pBLEScan->start(scanTime, false);
  pBLEScan->clearResults();
  delay(200);
#else
  delay(1000);
#endif
}
