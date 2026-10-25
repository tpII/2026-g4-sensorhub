#include "time_mgr.h"
#include "app_config.h"
#include "esp_netif_sntp.h"
#include "esp_log.h"
#include <sys/time.h>
#include <time.h>

static const char *TAG = "TIME_MGR";

// Sin RTC con bateria el reloj arranca en 1970; cualquier hora anterior a 2024-01-01 se considera no sincronizada
#define TIME_MGR_MIN_VALID_EPOCH_S      1704067200

esp_err_t time_mgr_init(TickType_t timeout_ticks) {
    esp_sntp_config_t config = ESP_NETIF_SNTP_DEFAULT_CONFIG(CONFIG_NTP_SERVER);
    esp_err_t ret = esp_netif_sntp_init(&config);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Fallo al iniciar SNTP: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = esp_netif_sntp_sync_wait(timeout_ticks);
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "Hora sincronizada con %s (epoch ms: %lld)", CONFIG_NTP_SERVER, time_mgr_now_ms());
    } else {
        ESP_LOGW(TAG, "Sin sincronizacion SNTP todavia; los payloads se envian sin 'ts' hasta sincronizar");
    }
    return ret;
}

bool time_mgr_is_synced(void) {
    return time(NULL) >= TIME_MGR_MIN_VALID_EPOCH_S;
}

int64_t time_mgr_now_ms(void) {
    if (!time_mgr_is_synced()) {
        return 0;
    }
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (int64_t)tv.tv_sec * 1000 + tv.tv_usec / 1000;
}
