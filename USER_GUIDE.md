# Diagrams Editor — Guida rapida

Crea diagrammi architetturali con l'AI e modificali visivamente nel browser.

---

## Requisiti

Solo **uv** — nient'altro.

```bash
# Installa uv (se non ce l'hai)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Setup iniziale (una volta per progetto)

Installa la skill di Claude Code nel tuo progetto. Questo fa sì che Claude sappia come creare i diagrammi:

```bash
uvx --from diagrams-editor diagrams skill-install
```

Poi riavvia Claude Code. Da quel momento Claude risponde a richieste come:
> "Crea un diagramma dell'architettura AWS con VPC, Lambda e RDS"

---

## Come si usa

### 1. Chiedi a Claude di creare il diagramma

Apri Claude Code nel tuo progetto e scrivi quello che vuoi:

```
Crea un diagramma dell'architettura del nostro servizio di autenticazione:
- CloudFront davanti
- ALB che bilancia su due istanze ECS
- RDS Aurora in una subnet privata
- SQS per gli eventi di login
```

Claude genera un file `.py` in `docs/architecture/` e ti dice il path.

### 2. Apri l'editor visuale

```bash
uvx --from diagrams-editor diagrams editor docs/architecture/<nome-diagramma>.py
```

Si apre automaticamente il browser su `http://localhost:8888` con il diagramma già caricato.

### 3. Modifica il layout

Nell'editor puoi:
- **Trascinare i nodi** per riorganizzare il layout
- **Doppio click** su un'etichetta per rinominarla
- **Aggiungere/rimuovere nodi** dalla palette a sinistra
- **Ridisegnare connessioni** con il tasto `E`

### 4. Scarica il PNG

Clicca il pulsante **⬇ Export PNG** in alto a destra.

---

## Comandi di riferimento

```bash
# Installa la skill nel progetto corrente
uvx --from diagrams-editor diagrams skill-install

# Installa la skill globalmente (tutti i progetti)
uvx --from diagrams-editor diagrams skill-install --global

# Apre l'editor con un file pre-caricato
uvx --from diagrams-editor diagrams editor docs/architecture/mio-diagramma.py

# Apre l'editor vuoto
uvx --from diagrams-editor diagrams editor

# Porta personalizzato (se 8888 è occupato)
uvx --from diagrams-editor diagrams editor docs/architecture/mio-diagramma.py --port 8889
```

> Se `diagrams-editor` è già una dipendenza del progetto (c'è nel `pyproject.toml`), sostituisci `uvx --from diagrams-editor` con `uv run`.

---

## Problemi comuni

| Problema | Soluzione |
|---|---|
| Porta 8888 già in uso | Aggiungi `--port 8889` al comando |
| Claude non riconosce la skill | Esegui di nuovo `skill-install` e riavvia Claude Code |
| File `.py` non trovato all'apertura | Verifica che il path sia corretto (relativo alla cartella corrente) |
| Comando non riconosciuto (`skill-install`, `editor <file>`) | Esegui `uv cache clean` e riprova |
