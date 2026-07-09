# Portal de Datos SNIGRD — API consultable (Datasette)

Capa de API avanzada del [Portal de Datos SNIGRD](https://github.com/masantizof/portal-datos-snigrd):
sirve las tablas municipales consolidadas (índices de riesgo, DANE, Sala de
Crisis, temperatura y amenaza por modelos de IDEAM, todas cruzadas por
código DIVIPOLA) vía [Datasette](https://datasette.io/), con una API JSON
que soporta **filtros y consultas SQL de sólo lectura** — a diferencia de
`api/datasets.json` del portal principal, que sólo sirve archivos completos.

Desplegado en [Render](https://render.com/) (Web Service, plan free, vía
Docker) a partir del Blueprint `render.yaml` en la raíz del repositorio
principal. Sólo lectura: la base se actualiza subiendo un `db.sqlite`
nuevo, generado con `scripts/construir_sqlite_datasette.py` — este
servicio no se conecta a IDEAM/DANE en vivo.

Nota: en el plan free de Render, el servicio se "duerme" tras ~15 min sin
tráfico y tarda unos 30s en despertar en la siguiente solicitud.

## Ejemplos de uso

```
GET /db/cruce_municipal.json?departamento=ANTIOQUIA
GET /db/cruce_municipal.json?_sort_desc=sala_crisis__n_emergencias&_size=10
GET /db.json?sql=SELECT+municipio,+TEXTO_AMENAZA+FROM+amenaza_deslizamientos+a+JOIN+municipios+m+ON+a.COD_DANE=m.divipola+WHERE+TEXTO_AMENAZA='ALTA'
```
