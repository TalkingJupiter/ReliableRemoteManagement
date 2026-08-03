#pragma once

#include <Arduino.h>

class OtaUpdater {
    public:
        void begin();
        void request(const char* url, const char* sha256Hex);
        void tick();
        void confirmHealthy();

        // True while a blocking update is running. The heartbeat task reads this
        // to go quiet so the partner takes over during the update + reboot.
        // static: callable as OtaUpdater::isUpdating() without an instance.
        static bool isUpdating();

    private:
        enum State {IDLE, REQUESTED};
        State _state = IDLE;

        char _url[128];
        char _sha256Hex[65];

        // The whole blocking download-verify-flash-reboot sequence.
        void runUpdate();
};