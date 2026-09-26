# Bitácora

Registro de avance semanal del proyecto. Las páginas 01 a 05 explican cómo funciona el sistema; acá anotamos qué fuimos haciendo, qué decidimos y con qué nos fuimos encontrando.

## Semana del 1 al 5 de septiembre

La cátedra nos asignó el tema y nos entregó el repositorio ya creado. Fue una semana de lectura, sobre todo para entender el Model Context Protocol, que ninguno conocía: qué son las tools, los resources y los prompts, y cómo hace un cliente para descubrirlos. En paralelo repasamos MQTT y el modelo de publicación y suscripción.

Decidimos arrancar por la documentación antes que por el código. La idea era dejar escritos la arquitectura y el contrato de comunicación para que después las tres partes (firmware, infraestructura y servidor MCP) pudieran avanzar en paralelo sin pisarse.

## Semana del 6 al 12 de septiembre

El 6 armamos la wiki con la navegación y las dos páginas de fundamentos, [[01. Visión y Arquitectura|01-Vision-y-Arquitectura]] y [[02. Tecnologías y Conceptos Clave|02-Tecnologias-y-Conceptos-Clave]]. Ahí quedó definida la arquitectura en cinco capas y la elección de EMQX en lugar de Mosquitto: el motor de reglas de EMQX escribe directo en InfluxDB, y eso nos evita tener que sumar un servicio intermedio al stack.

El 11 publicamos las dos páginas normativas, el [[contrato de mensajería MQTT|03-Contrato-de-Mensajeria-MQTT]] y el [[pipeline de ingesta|04-Infraestructura-y-Pipeline-EMQX-InfluxDB]]. La jerarquía de tópicos quedó como `sensorhub/<device_type>/<device_id>/<canal>`, con el `device_id` sacado de la MAC del chip, así el dispositivo se identifica solo y no hace falta repetir esos datos adentro del payload.

Escribiendo esa página apareció un problema que no habíamos visto. Con QoS 1 y retain activado, si el broker se reinicia el motor de reglas se vuelve a suscribir, recibe el último mensaje retenido y lo escribe en InfluxDB con la hora de ese momento y no la del evento original. En un sensor de movimiento eso es un falso positivo: una detección de hace dos horas queda registrada como si acabara de pasar. Por eso el PIR quedó con retain en false, aunque signifique perder un evento si justo el broker estaba caído en ese momento. La solución de fondo sería mandar el timestamp en el payload, pero eso obliga a sincronizar los ESP contra NTP, así que lo dejamos anotado como mejora para el firmware.

El 12 entregamos el Plan de Proyecto y el video.

## Semana del 13 al 19 de septiembre

El 17 subimos una primera versión del stack, trabajada en una rama aparte y mergeada a `main` con el PR #1. Es una base para ir probando, no la configuración final:

- `docker-compose` con EMQX 5.8 e InfluxDB 2.7, los dos configurándose solos al levantar.
- Un entrypoint que reemplaza las variables de entorno en las plantillas y engancha automáticamente las reglas que encuentre en `broker/templates/rules`, así agregar un dispositivo nuevo no obliga a tocar el `emqx.conf`.
- Las cuatro reglas del motor: `dht`, `pir`, `switch` y `status`.
- Cuatro simuladores en contenedores, para probar todo el camino sin tener el hardware.

Una decisión que tomamos armando las reglas es que el valor numérico lo calcula el motor y no el firmware. Los estados discretos se guardan dos veces, como texto (`state="on"`) y como entero (`value=1i`), porque InfluxDB necesita números para las funciones de agregación. En vez de pedirle al ESP que mande las dos cosas, la regla SQL deriva el entero con un `CASE WHEN` y el payload del dispositivo queda lo más chico posible.

El mismo día publicamos la página del [[servidor MCP|05-Servidor-MCP-y-LLM]]. Definimos ahí que el transporte va a ser Streamable HTTP y no stdio, porque el servidor va a correr como un contenedor más del stack y no como un subproceso que levanta el cliente.

## Semana del 20 al 26 de septiembre

Antes de ponernos con la implementación definitiva probamos el protocolo por separado. Armamos un servidor MCP mínimo con FastMCP y datos simulados en memoria, lo verificamos con el MCP Inspector, que permite invocar las tools a mano sin que haya un modelo en el medio, y después lo conectamos a un cliente con un modelo corriendo en local para ver el ciclo entero.

De eso sacamos dos cosas. La primera es que la descripción de cada tool es lo único que ve el modelo para decidir: no lee el código, lee el docstring y el esquema de parámetros. Dos tools con descripciones parecidas lo hacen elegir mal aunque estén bien programadas. La segunda es que conviene pensar bien los errores. Si la tool devuelve un error que además aclara qué valores sí son válidos, el modelo se corrige solo en el intento siguiente en vez de trasladarle el problema al usuario.

También dejamos armado el conjunto de consultas con el que vamos a medir la tasa de acierto. Preferimos definirlo ahora y no al final, porque después íbamos a terminar eligiendo las preguntas que ya sabemos que funcionan.

## Lo que sigue

Implementar el servidor MCP y subirlo al repositorio, cambiando los datos simulados por un suscriptor MQTT contra el stack. Después arrancar con el firmware de los nodos DHT y PIR.
