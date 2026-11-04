# Configurar Keycloak para el servidor MCP

Guía para dejar Keycloak listo, a mano desde la consola de administración, para que modelos clientes como claude.ai, ChatGPT, Claude Code o el MCP Inspector se conecten al servidor MCP de SensorHub.

## Qué hay que crear (y qué no)

| Qué | ¿Hace falta? | Por qué |
|:---|:---|:---|
| **Realm** `sensorhub` | Sí | Es el emisor de los tokens: el servidor MCP solo acepta tokens de `AUTH_PUBLIC_URL/realms/KC_REALM` |
| **Client scope** `sensorhub-mcp` con un mapper de audiencia | Sí | El servidor MCP rechaza los tokens cuya audiencia (`aud`) no sea su endpoint, `MCP_PUBLIC_URL` + `/mcp` |
| **Registro dinámico de clientes** (políticas de *Client registration*) | Sí | Los clientes MCP se registran solos la primera vez que se conectan. Con la configuración de fábrica, Keycloak rechaza ese registro |
| **Política de PKCE** | Recomendado | OAuth 2.1 exige PKCE `S256`. Los clientes MCP ya lo usan; la política lo hace obligatorio |
| **Usuario** | Sí, uno por persona | Es quien inicia sesión al conectar el cliente |
| Clients | **No** | Cada cliente crea el suyo al registrarse. No hay que crear ninguno a mano |
| Roles o grupos | **No** | El servidor MCP no lee roles. Como el realm es solo del MCP, tener usuario habilitado ya equivale a tener acceso (ver [Agregar otro usuario](#6-agregar-otro-usuario)) |

## 0. Antes de empezar

1. En `MCP/.env` tienen que estar `AUTH_PUBLIC_URL`, `MCP_PUBLIC_URL`, `KC_REALM` (por defecto `sensorhub`), `KC_ADMIN_USERNAME`, `KC_ADMIN_PASSWORD` y `KC_DB_PASSWORD`.
2. Levantar el compose: `docker compose up -d`.
3. Abrir la consola de administración en **http://localhost:8081** (solo responde desde la máquina del servidor) y entrar con `KC_ADMIN_USERNAME` / `KC_ADMIN_PASSWORD`.

> Todo lo que se configura acá queda guardado en la base de Keycloak (volumen `sensorhub_keycloak_db`). Se hace una sola vez y sobrevive a reinicios y recreaciones de los contenedores. Si se borra el volumen, hay que repetir la guía.

En los pasos que siguen, `<RECURSO_MCP>` es la URL completa del endpoint MCP, `MCP_PUBLIC_URL` + `MCP_HTTP_PATH`. Por ejemplo, `https://mcp.sensorhub.wgr.com.ar/mcp`.

## 1. Crear el realm

1. En el selector de realms (arriba a la izquierda): **Create realm**.
2. **Realm name**: `sensorhub`, igual que `KC_REALM`. **Enabled**: ON. **Create**.

Después, en **Realm settings** del realm nuevo:

| Pestaña | Campo | Valor |
|:---|:---|:---|
| General | Display name | `SensorHub` |
| Login | User registration | OFF (nadie se crea su propia cuenta) |
| Login | Forgot password | OFF |
| Login | Remember me | OFF |
| Login | Edit username | OFF |
| Security defenses → Brute force detection | Brute Force Mode | *Lockout temporarily* |
| | Max login failures | `5` |
| | Wait increment | `1` minuto |
| | Max wait | `15` minutos |
| Sessions | SSO Session Idle | `30` días |
| Sessions | SSO Session Max | `90` días |
| Tokens | Access Token Lifespan | `15` minutos |
| Localization | Internationalization | ON. Supported locales: `es`, `en`. Default locale: `es` |

Las sesiones largas evitan que los conectores pidan login cada pocas horas: el refresh token dura lo que dura la sesión. Los valores de sesión y tokens son opcionales. Con los de fábrica funciona igual, solo que hay que volver a iniciar sesión mucho más seguido.

## 2. Client scope con la audiencia del MCP

### Qué es la audiencia y por qué hace falta

La audiencia es el campo `aud` del access token: dice **para qué servicio se emitió el token**. Es el destinatario, así como `iss` (el emisor) es el remitente. Un token que Keycloak emite para un cliente se ve más o menos así:

```json
{
  "iss": "https://auth.ejemplo.com/realms/sensorhub",
  "aud": "https://mcp.ejemplo.com/mcp",
  "sub": "id-del-usuario",
  "azp": "id-del-cliente (claude.ai, ChatGPT...)",
  "exp": 1793750400
}
```

En cada pedido, el servidor MCP ([`verifier.py`](../sensorhub_mcp/auth/verifier.py)) comprueba la firma, el emisor y el vencimiento. Además exige que `aud` sea exactamente `<RECURSO_MCP>`. La [especificación de autorización de MCP](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) obliga a hacer esta comprobación: el cliente pide el token para un recurso concreto (RFC 8707) y el servidor rechaza los tokens que no son para él.

Esta comprobación hace que un token sirva solo para el servicio para el que se emitió. Sin ella, al MCP le serviría cualquier token válido del realm:

- Si el mismo Keycloak se usa mañana para otra aplicación (p. ej. un dashboard), un token de esa aplicación permitiría también operar los actuadores.
- Un servicio que recibió un token tuyo para otra cosa podría reenviarlo al MCP y usarlo en tu nombre.

**Por qué hay que configurarla:** Keycloak no pone la URL del MCP en `aud` por su cuenta. En sus tokens, `aud` queda vacío o con `account`, así que el servidor los rechazaría todos. El client scope de este paso agrega la audiencia con un mapper. Como el scope es *Default*, lo reciben todos los clientes, incluidos los que se registran solos. No hay un client al que asignárselo a mano.

**Consecuencia práctica:** la audiencia del mapper tiene que coincidir **exactamente** con `MCP_PUBLIC_URL` + `MCP_HTTP_PATH`. Si no coincide, el login funciona pero el MCP responde 401 a todos los pedidos.

### Configuración

1. **Client scopes → Create client scope**:
   - **Name**: `sensorhub-mcp`
   - **Type**: **Default**. Esto lo agrega a los scopes por defecto del realm, así lo reciben los clientes que se registran solos.
   - **Protocol**: OpenID Connect
   - **Display on consent screen**: ON
   - **Consent screen text**: `Consultar los sensores y operar los actuadores de SensorHub`
   - **Include in token scope**: ON
   - **Save**.
2. En el scope recién creado: **Mappers → Configure a new mapper → Audience**:
   - **Name**: `audiencia-mcp`
   - **Included Client Audience**: vacío
   - **Included Custom Audience**: `<RECURSO_MCP>`, exacta, con `https://` y `/mcp` y sin `/` al final
   - **Add to ID token**: OFF
   - **Add to access token**: ON
   - **Add to token introspection**: ON
   - **Save**.

Para confirmar que quedó como scope por defecto, ir a **Realm settings → Client scopes** (o **Client scopes**, columna *Assigned type*): `sensorhub-mcp` tiene que figurar como *Default*.

> Si cambia `MCP_PUBLIC_URL` (otro dominio, un túnel nuevo), hay que actualizar *Included Custom Audience* en este mapper. Si no, el servidor rechaza todos los tokens.

## 3. Registro dinámico de clientes (DCR)

Los clientes MCP no traen un *client ID* propio de este servidor. La primera vez que se conectan, se registran solos y sin credenciales (registro anónimo, RFC 7591) y obtienen uno. Sin este registro, cada cliente nuevo obligaría a crear a mano un client en Keycloak y cargar su ID en el cliente, y no todos los clientes lo permiten.

La idea es que **cualquier cliente MCP** pueda registrarse. Lo que protege el acceso es el login: un cliente registrado no puede hacer nada hasta que un usuario del realm inicia sesión y acepta la pantalla de consentimiento.

**Clients → Client registration → Anonymous access policies**:

1. **Trusted Hosts**: **borrarla** (menú ⋮ o ícono de papelera → *Delete*). Esta política solo acepta registros que vienen de una lista de hosts o IPs, y con la configuración de fábrica (lista vacía) bloquea a todos los clientes.
2. **Allowed Registration Web Origins**:
   - **Web Origins**: `http://localhost:6274`, el MCP Inspector.
   - Solo afecta a los clientes que se registran desde una página web en el navegador, por CORS. claude.ai, ChatGPT y Claude Code se registran desde su servidor o su programa y no pasan por acá. Si algún día usás otro cliente web, se suma su origen.
   - **Save**.
3. Las demás políticas quedan como vienen, y conviene no tocarlas:
   - **Consent Required**: cada cliente nuevo muestra, después del login, qué aplicación pide acceso. Es la defensa principal ahora que cualquiera puede registrar un cliente (ver abajo).
   - **Allowed Client Scopes**: los clientes reciben solo los scopes por defecto, entre ellos `sensorhub-mcp`.
   - **Max Clients Limit** (200 por defecto): pone un tope a cuántos clientes puede crear alguien registrando en masa.
   - **Full Scope Disabled** y **Allowed Protocol Mapper Types**: impiden que un cliente se registre pidiendo más permisos o mappers propios.

> **El riesgo de abrir el registro:** un tercero puede registrar un cliente que se llame, por ejemplo, "Claude", y apunte a un dominio suyo. Después te manda el enlace de login. Si iniciás sesión **y aceptás el consentimiento**, ese tercero obtiene un token para usar el MCP. Por eso, en la pantalla de consentimiento conviene mirar la dirección a la que vuelve el login (la barra del navegador, al terminar). Si no iniciaste vos la conexión desde un cliente, rechazá el pedido. También conviene revisar de vez en cuando **Clients** y borrar los que no reconozcas.
>
> Si se prefiere cerrar el registro a ciertos clientes, en vez de borrar *Trusted Hosts* hay que editarla: **Host Sending Client Registration Request Must Match** en OFF, los hosts permitidos en **Trusted Hosts** (p. ej. `claude.ai`, `chatgpt.com`, `localhost`, `127.0.0.1`) y **Client URIs Must Match** en ON.

## 4. PKCE obligatorio

**Realm settings → Client policies**:

1. Pestaña **Profiles → Create client profile**:
   - **Name**: `pkce-s256`. **Save**.
   - **Add executor** → tipo **pkce-enforcer**, **Auto-configure**: ON. **Add**.
2. Pestaña **Policies → Create client policy**:
   - **Name**: `pkce-todos-los-clientes`. **Save**.
   - **Add condition** → **any-client**. **Add**.
   - **Add client profile** → `pkce-s256`. **Add**.

## 5. Crear el usuario

1. **Users → Add user** (o **Create new user**):
   - **Username**: p. ej. `sensorhub`
   - **Email**, **First name**, **Last name**: completarlos. Si faltan, el perfil de usuario de Keycloak los pide en el primer login.
   - **Email verified**: ON
   - **Create**.
2. Pestaña **Credentials → Set password**:
   - Una contraseña de 12 caracteres como mínimo.
   - **Temporary**: OFF si la contraseña es tuya. ON si se la pasás a otra persona, para que la cambie en su primer login.
   - **Save**.

Con esto ya se puede conectar un cliente (ver [Conectar un cliente](../README.md#conectar-un-cliente)).

## 6. Agregar otro usuario

Se repite el paso 5 con otro *username*. No hace falta tocar nada más: sin registro abierto, los únicos usuarios del realm son los que crea un administrador, y todo usuario habilitado puede usar el MCP.

Lo habitual es poner **Temporary: ON** en la contraseña y pasársela a la persona: en su primer login Keycloak le pide una nueva.

Para dar acceso de administración a otra persona (que pueda crear usuarios del realm `sensorhub` sin ser el admin general), a su usuario se le asignan en **Role mapping → Assign role → Filter by clients** los roles `realm-management` → `manage-users` y `view-users`. La consola de ese realm queda en `http://localhost:8081/admin/sensorhub/console`.

Para **quitar el acceso** a un usuario:

1. **Users → (usuario) → Enabled**: OFF. Así ya no puede iniciar sesión ni renovar tokens.
2. **Sessions → Sign out** para cortar las sesiones abiertas. Los access tokens ya emitidos siguen valiendo hasta que vencen, como máximo 15 minutos.

Para borrarlo del todo, **Delete**.

## 7. Comprobar que funciona

Con el compose levantado:

```bash
# Metadatos del servidor MCP: tiene que listar el realm como authorization_servers
curl -s https://<dominio-mcp>/.well-known/oauth-protected-resource/mcp

# Metadatos del realm: tiene que tener registration_endpoint y S256 en code_challenge_methods_supported
curl -s https://<dominio-auth>/realms/sensorhub/.well-known/openid-configuration
```

Después, conectar un cliente (el MCP Inspector es el más cómodo para probar). Al terminar el login, en **Clients** aparece el cliente que se registró. Para mirar un token, en ese cliente: **Client scopes → Evaluate**, elegir el usuario y abrir **Generated access token**. Tiene que tener `"aud": "<RECURSO_MCP>"` y `iss` igual a `AUTH_PUBLIC_URL/realms/sensorhub`.

| Síntoma | Causa probable |
|:---|:---|
| El cliente falla al registrarse (`Policy 'Trusted Hosts' rejected request...`) | Paso 3: no se borró la política *Trusted Hosts* |
| Un cliente web falla al registrarse por CORS | Paso 3: falta su origen en *Allowed Registration Web Origins* |
| Login correcto, pero el servidor responde 401 | Paso 2: la audiencia no coincide exacta con `<RECURSO_MCP>`, o `sensorhub-mcp` no es scope *Default*. También puede ser que `AUTH_PUBLIC_URL` en `.env` no coincida con la URL pública real de Keycloak (emisor distinto) |
| `invalid_redirect_uri` en el login | El cliente se registró con otra `redirect_uri`: borrarlo en **Clients** y volver a conectar |
| `Account is temporarily disabled` | Protección contra fuerza bruta. Esperar, o liberar al usuario desde **Users → (usuario)** |

## Opcional: restringir el acceso por rol

Solo hace falta si el realm se va a usar también para otra cosa y no todos sus usuarios tienen que entrar al MCP. Hay dos caminos:

- **En el servidor MCP:** crear un rol de realm (p. ej. `mcp-user`), asignarlo a los usuarios y hacer que [`verifier.py`](../sensorhub_mcp/auth/verifier.py) rechace los tokens sin ese rol en `realm_access.roles`. Requiere cambiar código.
- **En Keycloak:** en **Authentication**, duplicar el flujo *browser* y agregar, después del formulario de usuario y contraseña, un sub-flujo *Conditional* con **Condition - User Role** (rol `mcp-user`, *Negate output*: ON) y **Deny access**. Después, asignar el flujo nuevo como *Browser flow* del realm.

Mientras el realm sea solo del MCP, no vale la pena: habilitar o deshabilitar al usuario cumple la misma función.
