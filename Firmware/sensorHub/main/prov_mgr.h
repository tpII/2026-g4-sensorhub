#ifndef PROV_MGR_H
#define PROV_MGR_H

// Provisioning WiFi por BLE con la app "ESP BLE Provisioning" de Espressif. Requiere wifi_mgr_init().
//
// Con credenciales guardadas libera la memoria del stack BLE (no se usa en ejecucion normal) y retorna.
// Sin credenciales anuncia el dispositivo "<CONFIG_PROV_BLE_NAME_PREFIX><tipo>_<ultimos 4 hex de la MAC>"
// por BLE (Security 1 con PoP CONFIG_PROV_POP). La app envia SSID y contraseña, el componente prueba
// la conexion y le informa a la app si fallo (permite reintentar); al conectar reinicia el equipo. No retorna.
void prov_mgr_run(void);

#endif // PROV_MGR_H
