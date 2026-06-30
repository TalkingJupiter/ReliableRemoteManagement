#include "RelayControl.h"
#include "DeviceConfig.h"

void RelayControl::begin(int relayAPin, int relayBPin, bool activeLow){
    _pinA = relayAPin;
    _pinB = relayBPin;
    _activeLow = activeLow;

    if (_pinA >= 0) pinMode(_pinA, OUTPUT);
    if (_pinB >= 0) pinMode(_pinB, OUTPUT);

    //Default: both relays are OFF (disconnected)
    if (_pinA >= 0) writeRelay(_pinA, false);
    if (_pinB >= 0) writeRelay(_pinB, false);
    _owner = BusOwner::NONE;
}

void RelayControl::writeRelay(int pin, bool on){
    if (pin<0) return;

    if(_activeLow){
        digitalWrite(pin, on ? LOW : HIGH);
    } else {
        digitalWrite(pin, on ? HIGH : LOW);
    }
}

void RelayControl::setOwner(BusOwner newOwner){
    if (newOwner == _owner) return;

    if (_pinA >= 0) writeRelay(_pinA, false);
    if (_pinB >= 0) writeRelay(_pinB, false);
    delay(BREAK_BEFORE_MAKE_MS);

    if (newOwner == BusOwner::A && _pinA >= 0) writeRelay(_pinA, true);
    
    if (newOwner == BusOwner::B && _pinB >=0) writeRelay(_pinB, true);

    _owner = newOwner;
}