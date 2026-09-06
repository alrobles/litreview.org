# Integrating the DiDAL Review Protocol into LitReview — Design Plan

**Fecha:** 2026-09-06
**Estado:** propuesta / diseño (sin implementar todavía)
**Dominio:** litreview.org (public) + litreview-devel (private)
**Base actual:** screening de 1 modelo (minimax-m3:free → nemotron fallback)

---

## 1. Contexto y objetivo

Hoy el "revisor virtual" de LitReview es una sola llamada LLM que produce un
impact index 1-10 + 5 sub-scores (originality, methodological_rigor, clarity,
relevance, bibliography) + red flags + one-line, con un prompt fijo
(`app/screening.py` → `SCORE_SYSTEM`). Es rápido, barato y ya funciona, pero:

- Es **una sola opinión** de un solo modelo, sin dialéctica ni verificación de fuentes.
- El score puede sorprender al autor porque no entiende QUÉ se evaluó ni CÓMO.
- No hay trazabilidad de evidencia (¿por qué 3.5 en rigor?).

`ecoseek.org` ya tiene un protocolo maduro de revisión multi-agente: **DiDAL
(Dialectical Dual-Agent Loop)** — pipeline de 7 stages
(`emily/plugins/ecoseek/protocol.py`):

```
classify → frame_task → retrieve → expert_draft → critique → revise → report
```

Este plan propone integrar DiDAL como el **motor del revisor virtual de
LitReview**, manteniendo el impact index como salida, pero generado por un
proceso dialéctico con verificación de evidencia y transparente al autor.

---

## 2. Qué es DiDAL (referencia fiel)

Del código de ecoseek (`emily/plugins/ecoseek/protocol.py`, línea 4):

| Stage | Responsabilidad | Fuente |
|-------|----------------|--------|
| 0. classify | Determina complejidad/modo (direct vs didal vs didal_literature) | classifier.py |
| 1. frame_task | Arma el task object con el contexto de la clasificación | — |
| 2. retrieve | Busca literatura real: OpenAlex, Semantic Scholar, GBIF Literature, crawl4ai/CrossRef | retrieval.py |
| 3. expert_draft | El agente redacta la revisión con la evidencia recuperada | LLM (Hermes beta / local fallback) |
| 4. critique | Un segundo agente critica el draft (dialéctica) | LLM |
| 5. revise | Se integra la crítica en la versión final | LLM |
| 6. report | Ensambla el entregable (verdict + referencias + notas) | helper |

El skill `manuscript-didal-review` (mesh) extiende esto a agentes en OTROS
nodos Tailscale (alpha = narrative critic, gamma = citations/methods critic),
con verificación contra PubMed/CrossRef.

**Para LitReview no necesitamos la versión multi-nodo mesh** (eso es para
revisar manuscritos del equipo). Necesitamos la esencia: **dialéctica
(draft → critique → revise) + evidencia recuperada (retrieve) + reporte
transparente**, todo corriendo en el contenedor de litreview.

---

## 3. Arquitectura propuesta

### 3.1 Pipeline de screening ampliado (v6)

```
submit
  │
  ├─ [gate 1] SEGURIDAD  (determinista, ya implementado — regex)
  ├─ [gate 2] SOFT       (heurística spam, ya implementado)
  │
  ├─ [gate 3] REVISOR VIRTUAL DiDAL  ← NUEVO (reemplaza la single-call)
  │    ├─ 0. classify    → modo (didal_literature si hay bibliografía)
  │    ├─ 2. retrieve    → OpenAlex + CrossRef (gratis, sin key dura)
  │    │                   busca por título/autores/área del review
  │    ├─ 3. draft       → el revisor redacta su evaluación con evidencia
  │    ├─ 4. critique    → segundo prompt critica el draft (dialéctica)
  │    ├─ 5. revise      → versión final consolidada
  │    └─ 6. score       → impact_index + 5 sub-scores + confidence +
  │                        referencias recuperadas + juicio del crítico
  │
  ├─ [gate 4] HUMANO (moderador) — el veredicto final SIEMPRE humano
  │
  └─ notificación email (aceptado/rechazado)
```

### 3.2 Impact index — definición estable (NO cambia la semántica)

El impact index sigue siendo **un predictor 1-10 de impacto/citabilidad
potencial DEL TEXTO, no un juicio de valor sobre el autor ni un factor de
impacto real**. Con DiDAL la diferencia es que cada sub-score viene
justificado por:

- evidencia recuperada de OpenAlex/CrossRef (¿el review cita/ignora la
  literatura clave del área?),
- el draft del revisor (qué leyó, qué encontró),
- la crítica (segunda opinión dialéctica).

### 3.3 Costo y latencia

| | Hoy (v5) | DiDAL (v6) |
|---|---|---|
| LLM calls | 1 | ~3-4 (draft, critique, revise/scoring) |
| Latencia | ~2-10s | ~15-40s |
| Costo | minimax-m3:free (0) | mismos free models → $0 |
| Evidencia | ninguna | OpenAlex/CrossRef (gratis, rate-limit generoso) |

Latencia aceptable: el screening corre en BackgroundTask tras el submit; el
admin ve el resultado cuando carga la cola. La UI ya muestra "Screening…".

---

## 4. Experiencia del autor (TRANSPARENCIA — el "no te lleves sorpresa")

El corazón del pedido: **que quien somete sepa exactamente a qué se somete.**

### 4.1 Página pública "Review process" (review-process.html)

Nueva página en litreview.org (link en nav + en submit.html) que documenta
con honestidad:

1. **Cómo funciona el revisor virtual** — 3 capas (seguridad, spam, score) +
   diagrama del pipeline.
2. **Qué es el impact index** — definición, escala 1-10, los 5 sub-scores,
   confidence, red flags, one-line. QUÉ SIGNIFICA y QUÉ NO (no es factor de
   impacto real, no es juicio al autor, es predictor del texto).
3. **El protocolo DiDAL** — explicación en lenguaje simple: un revisor
   redacta, un segundo revisor critica, se concilia, y se verifican fuentes
   en OpenAlex/CrossRef. (Escalado desde ecoseek.org.)
4. **Reglas de oro para que el score no sorprenda:**
   - Con bibliografía actual y relevante → sub-score de bibliography alto.
   - Con métodos claros y limitaciones → rigor alto.
   - Texto genérico sin referencias → score bajo (esperado, no castigo).
   - El score es ASESORÍA: la decisión la toma un humano moderador.
5. **Transparencia de datos**: qué se guarda (submitted_by, screening.json,
   uno_line adjudicada por el modelo, red flags) y que el autor puede pedir
   re-screening.

### 4.2 En submit.html

- Un bloque visible "How your review will be scored" junto al botón Submit:
  los 5 criterios con su peso, un aviso "las revisiones sin bibliografía
  suelen recibir scores bajos", y el enlace a review-process.html.
- El texto del consentimiento ya menciona "AI assistance" — añadir una línea:
  "I understand my submission will be assessed by an automated AI review
  (DiDAL protocol) and that the final decision rests with human moderators."

### 4.3 El email de rechazo

Reutilizar el servicio de email para incluir en el email de rechazo:
- el impact_index + los 5 sub-scores (para que el autor vea QUÉ puntuó bajo),
- la one-line del revisor,
- el enlace a review-process.html ("cómo se calculó esto").

---

## 5. Implementación (por fases)

### Fase A — Transparencia primero (deploy inmediato, sin tocar scoring)
- Crear review-process.html (estático, estilo existente).
- Añadir link en nav (About → +Review process) y en submit.html.
- Añadir la línea al consentimiento.
- Deploy: solo frontend → push al public + bind-mount ya lo sirve.
- **Beneficio inmediato**: el autor ya sabe a qué se somete, hoy.

### Fase B — DiDAL dentro del contenedor (v6)
- Nuevo módulo `app/didal.py`: port de los stages esenciales
  (classify → retrieve → draft → critique → revise → score) adaptado a
  litreview (single-node, sin mesh, sin Hermes beta).
- `retrieval.py` (nuevo): OpenAlex API (works?search=...) + CrossRef
  (query.bibliographic) — gratis, best-effort, con timeout y fallback a
  "sin evidencia recuperada" (no bloquea el score).
- Cambiar `screening.py` → `scientific_score()` delega en didal.py.
- El screening.json gana: `evidence[]`, `critique` (texto del crítico),
  `report` (justificación por sub-score).
- Admin UI: mostrar evidence + critique en el panel.

### Fase C — Transparencia en el output (público)
- La página abs.html muestra (junto al impact_index badge) un mini-desglose:
  "Methodological rigor: 6/10 — the review does not describe its search
  strategy" (texto del report).
- Email de rechazo con desglose.
- Opcional: endpoint público `/review/{id}/screening` con el screening
  desglosado (solo reviews publicadas).

---

## 6. Riesgos y decisiones críticas

1. **OpenAlex/CrossRef como "verdad"** — NO. La evidencia recuperada es
   contexto para el revisor, no un juicio de plagio ni de exhaustividad.
   El retrieve puede fallar (timeout, red) → degradar a scoring sin
   evidencia (como hoy), nunca bloquear.

2. **Sesgo de los modelos free** — ya documentado en v5; DiDAL ayuda porque
   la dialéctica (draft + critique) reduce el sesgo de un solo modelo, pero
   no lo elimina. La confidence y el modelo quedan grabados SIEMPRE.

3. **Latencia** — 15-40s en background es aceptable; NO bloquear el submit.
   El admin ya lidia con "Screening…". Si algún stage tarda >60s, timeout y
   degradación parcial.

4. **El humano manda** — DiDAL informa, el moderador decide. El auto-reject
   físico sigue INACTIVO (decisión previa) y NO se activa con DiDAL.

5. **Reuso del código de ecoseek** — portar con licencia clara: ecoseek es
   del mismo autor (alrobles), sin problema de atribución; pero el módulo de
   litreview debe ser self-contained (sin dependencias de emily/plugins).

6. **back-compat** — screening.json v5 sin evidence/critique debe renderizar
   igual (campos opcionales en la UI).

---

## 7. Alcance fuera (explícitamente NO en este plan)

- Multi-nodo mesh (alpha/gamma) para revisar manuscritos del EQUIPO — eso
  queda en manuscript-didal-review, no en litreview.
- Human-in-the-loop con encuesta (survey) post-OAuth — pendiente aparte.
- Publicar el screening completo al público (solo desglose agregado).