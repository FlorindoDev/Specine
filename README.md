# Specine: varianti MetaGPT e Tester Skill

## Indice

- [Obiettivo](#obiettivo)
- [Modalità di esecuzione](#modalità-di-esecuzione)
  - [Base (baseline)](#avvio-della-baseline-base)
  - [Variante A MetaGPT nel Coder Agent](#avvio-della-variante-a)
  - [Variante B MetaGPT nel Tester Agent](#variante-b-metagpt-nel-tester-agent)
  - [Variante C MetaGPT nel Coder e Tester Skill](#variante-c-metagpt-nel-coder-e-tester-skill)
  - [Variante D MetaGPT nel Coder e nel Tester](#variante-d-metagpt-nel-coder-e-nel-tester)
  - [Variante E Tester Skill](#variante-e-tester-skill)
  - [Variante F integrazione completa](#variante-f-integrazione-completa)
- [Preparazione dell'ambiente](#preparazione-dellambiente)
- [Modello predefinito](#modello-predefinito)
- [API compatibili](#api-compatibili)
- [File avviabili e flag](#file-avviabili-e-flag)
- [Benchmark disponibili](#benchmark-disponibili)
- [Download dei dataset](#download-dei-dataset)
- [Esecuzione rapida](#esecuzione-rapida)
- [Risultati](#risultati)
- [Cache dell'Initial Code e parallelismo](#cache-dellinitial-code-e-parallelismo)
- [Configurazione completa del run predefinito](#configurazione-completa-del-run-predefinito)

![Varianti architetturali A, B e C di Specine](Figures/architecture-variants-a-c.png)

![Varianti architetturali D, E e F di Specine](Figures/architecture-variants-d-f.png)

## Obiettivo

Questo fork confronta la generazione originale di Specine con varianti che evolvono il workflow del Coder Agent e del Tester Agent.

La [modalità Base](#avvio-della-baseline-base) usa agenti diretti. Le varianti A–F combinano in modo controllato tre componenti riutilizzabili: workflow MetaGPT del Coder, workflow MetaGPT del Tester e Tester Skill.

I benchmark disponibili sono esclusivamente APPS, APPS-Eval e CodeContests-Raw.

## Modalità di esecuzione

La **Base (baseline)** è la versione di riferimento: esegue il workflow originale di Specine, nel quale il Coder Agent genera il codice con una sola chiamata al modello. Si avvia con `--variant base`; poiché `base` è il valore predefinito, il flag può essere omesso. Vedere [Avvio della baseline](#avvio-della-baseline-base).

La **variante A** mantiene il Tester Agent e il processo di allineamento di Specine invariati, ma sostituisce la generazione diretta del Coder Agent con un sotto-workflow MetaGPT: Product Manager, Architect, Project Manager ed Engineer lavorano in sequenza prima della generazione del codice. Vedere [Avvio della variante A](#avvio-della-variante-a).

La **variante B** mantiene il Coder Agent diretto e usa il workflow MetaGPT nel Tester Agent. Test Analyst, Test Designer, Test Generator e Test Reviewer / Validator interpretano i vincoli, progettano i casi, calcolano gli output attesi e validano il JSON finale.

La **variante C** combina il Coder MetaGPT della variante A con un Tester Agent diretto guidato dalla Tester Skill. La Skill impone estrazione dei requisiti, casi base/boundary e avversariali, calcolo indipendente degli output e validazione.

La **variante D** usa entrambi i workflow MetaGPT. I quattro ruoli del Coder producono l'Initial Code; i quattro ruoli del Tester producono e revisionano i Generated Tests.

La **variante E** mantiene il Coder Agent diretto e applica solo la Tester Skill. Il confronto con Base isola quindi l'effetto della Skill sulla qualità dei test.

La **variante F** integra entrambi i workflow MetaGPT e inietta la Tester Skill in tutte le fasi del workflow Tester. È la configurazione più completa e più costosa in chiamate LLM.

La Skill predefinita vive in `tester_skill.py`: modificare `DEFAULT_TESTER_SKILL` oppure passare un'altra istanza di `TesterSkill` a `create_tester_workflow` per sperimentare istruzioni diverse senza cambiare il workflow.

I risultati della Base servono come termine di confronto per misurare l'effetto delle altre modalità. Per un confronto corretto bisogna usare lo stesso modello, lo stesso benchmark e lo stesso numero massimo di iterazioni; deve cambiare solo il workflow scelto.

## Preparazione dell'ambiente

Eseguire tutti i comandi dalla cartella principale del progetto. È richiesto Python 3.10.

### Windows PowerShell

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Se PowerShell non consente l'attivazione dell'ambiente virtuale, usare direttamente il suo interprete.

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Linux e macOS

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Le dipendenze installano PyTorch 2.5.1 per CUDA 12.4. Per eseguire localmente un modello da 7 miliardi di parametri è consigliata una GPU NVIDIA.

## Modello predefinito

Il modello predefinito è `deepseek-coder-7b-instruct-v1.5`. Tutti i comandi riportati sotto usano DeepSeek senza richiedere l'opzione `--model_name`.

Dopo avere installato le dipendenze e attivato l'ambiente virtuale, scaricare il modello con lo script incluso nel progetto:

```bash
python download_model.py
```

Lo script scarica l'intero repository `deepseek-ai/deepseek-coder-7b-instruct-v1.5` nella posizione attesa dal programma:

```text
LLMs/deepseek-coder-7b-instruct-v1.5/
```

La directory deve contenere configurazione, tokenizer e pesi del modello. Un download interrotto può essere ripreso eseguendo nuovamente lo stesso comando; i file già aggiornati non vengono scaricati di nuovo.

Qwen2.5-Coder-7B-Instruct può essere eseguito localmente con il nome `Qwen2.5-Coder-7B-Instruct` oppure tramite OpenRouter. Per usarlo via API, configurare `OPENROUTER_API_KEY` e impostare lo slug Qwen in `OPENROUTER_MODEL`.

```powershell
$env:OPENROUTER_API_KEY="<api-key>"
$env:OPENROUTER_MODEL="qwen/qwen2.5-coder-7b-instruct"
python alignment.py --model_name openrouter --benchmark apps --save_dir qwen_openrouter_apps
```

## API compatibili

Il progetto usa il client Python OpenAI e supporta questi provider:

| Provider | Valore `--model_name` | Variabili richieste | Endpoint predefinito |
| --- | --- | --- | --- |
| OpenAI | `gpt-4o-mini-2024-07-18` | `OPENAI_API_KEY` | Endpoint ufficiale del client OpenAI |
| Google Gemini | `gemini-1.5-flash-002` | `GEMINI_API_KEY` | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| OpenRouter | `openrouter` | `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | `https://openrouter.ai/api/v1` |

Le variabili possono essere definite nel sistema oppure in un file `.env` nella directory principale. Copiare `.env.example` in `.env` e compilare solo il provider usato.

Con OpenRouter, `OPENROUTER_MODEL` accetta qualsiasi slug testuale disponibile nel [catalogo OpenRouter](https://openrouter.ai/models) e compatibile con Chat Completions. Esempio:

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=qwen/qwen2.5-coder-7b-instruct
OPENROUTER_APP_TITLE=Specine
```

```powershell
python alignment.py --model_name openrouter --benchmark apps --save_dir openrouter_apps
```

`OPENROUTER_HTTP_REFERER` e `OPENROUTER_APP_TITLE` sono opzionali. `OPENROUTER_BASE_URL`, `GEMINI_BASE_URL` e `OPENAI_BASE_URL` permettono di sostituire gli endpoint predefiniti. OpenRouter è compatibile con il client OpenAI usato dal progetto e restituisce `prompt_tokens` e `completion_tokens`, quindi il conteggio token resta attivo. Vedere la [documentazione OpenRouter per OpenAI SDK](https://openrouter.ai/docs/guides/community/openai-sdk).

## File avviabili e flag

Le CLI supportate sono `alignment.py` per eseguire i benchmark e `download_datasets.py` per scaricare i dataset. `eval_code.py` conserva un entry point legacy: la valutazione usata dal flusso corrente viene già eseguita internamente da `alignment.py`, quindi non è necessario avviarlo separatamente.

### alignment.py

<table>
  <thead>
    <tr>
      <th>File</th>
      <th>Flag</th>
      <th>Obbligatorio</th>
      <th>Default</th>
      <th>Valori ammessi</th>
      <th>Funzione</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><code>alignment.py</code></td>
      <td><code>-h</code>, <code>--help</code></td>
      <td>No</td>
      <td>Nessuno</td>
      <td>Nessuno</td>
      <td>Mostra la guida della CLI e termina.</td>
    </tr>
    <tr>
      <td><code>alignment.py</code></td>
      <td><code>--benchmark</code></td>
      <td>Sì</td>
      <td>Nessuno</td>
      <td><code>apps</code>, <code>apps-eval</code>, <code>codecontests-raw</code></td>
      <td>Seleziona il benchmark da eseguire.</td>
    </tr>
    <tr>
      <td><code>alignment.py</code></td>
      <td><code>--model_name</code></td>
      <td>No</td>
      <td><code>deepseek-coder-7b-instruct-v1.5</code></td>
      <td><code>deepseek-coder-7b-instruct-v1.5</code>, <code>Qwen2.5-Coder-7B-Instruct</code> (locale), <code>gpt-4o-mini-2024-07-18</code>, <code>gemini-1.5-flash-002</code>, <code>openrouter</code></td>
      <td>Seleziona il modello locale o il backend API.</td>
    </tr>
    <tr>
      <td><code>alignment.py</code></td>
      <td><code>--variant</code></td>
      <td>No</td>
      <td><code>base</code></td>
      <td><code>base</code>, <code>A</code>, <code>B</code>, <code>C</code>, <code>D</code>, <code>E</code>, <code>F</code></td>
      <td><code>A</code>: Coder MetaGPT; <code>B</code>: Tester MetaGPT; <code>C</code>: Coder MetaGPT + Tester Skill; <code>D</code>: entrambi MetaGPT; <code>E</code>: Tester Skill; <code>F</code>: entrambi MetaGPT + Tester Skill.</td>
    </tr>
    <tr>
      <td><code>alignment.py</code></td>
      <td><code>--save_dir</code></td>
      <td>Sì</td>
      <td>Nessuno</td>
      <td>Nome di directory</td>
      <td>Imposta il nome della cartella in cui salvare i risultati.</td>
    </tr>
    <tr>
      <td><code>alignment.py</code></td>
      <td><code>--max_iter</code></td>
      <td>No</td>
      <td><code>10</code></td>
      <td>Numero intero</td>
      <td>Imposta il numero massimo di iterazioni per ogni problema.</td>
    </tr>
    <tr>
      <td><code>alignment.py</code></td>
      <td><code>--debug</code></td>
      <td>No</td>
      <td>Disattivato</td>
      <td>Flag senza valore</td>
      <td>Stampa prompt e risposte del modello durante l'esecuzione.</td>
    </tr>
  </tbody>
</table>

### download_datasets.py

<table>
  <thead>
    <tr>
      <th>File</th>
      <th>Flag</th>
      <th>Obbligatorio</th>
      <th>Default</th>
      <th>Valori ammessi</th>
      <th>Funzione</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><code>download_datasets.py</code></td>
      <td><code>-h</code>, <code>--help</code></td>
      <td>No</td>
      <td>Nessuno</td>
      <td>Nessuno</td>
      <td>Mostra la guida della CLI e termina.</td>
    </tr>
    <tr>
      <td><code>download_datasets.py</code></td>
      <td><code>--benchmark</code></td>
      <td>No</td>
      <td>Menu interattivo</td>
      <td><code>apps</code>, <code>apps-eval</code>, <code>codecontests-raw</code></td>
      <td>Scarica il dataset associato al benchmark. Se viene omesso, mostra il menu di scelta.</td>
    </tr>
    <tr>
      <td><code>download_datasets.py</code></td>
      <td><code>--force</code></td>
      <td>No</td>
      <td>Disattivato</td>
      <td>Flag senza valore</td>
      <td>Riscarica e sostituisce il dataset anche quando il file esiste già.</td>
    </tr>
  </tbody>
</table>

### eval_code.py

Questa tabella descrive esclusivamente l'entry point legacy.

<table>
  <thead>
    <tr>
      <th>File</th>
      <th>Flag</th>
      <th>Obbligatorio</th>
      <th>Default</th>
      <th>Valori ammessi</th>
      <th>Funzione</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><code>eval_code.py</code> legacy</td>
      <td><code>-h</code>, <code>--help</code></td>
      <td>No</td>
      <td>Nessuno</td>
      <td>Nessuno</td>
      <td>Mostra la guida della CLI e termina.</td>
    </tr>
    <tr>
      <td><code>eval_code.py</code> legacy</td>
      <td><code>--data_name</code></td>
      <td>No</td>
      <td>Stringa vuota</td>
      <td>Qualsiasi stringa. I valori previsti dalla vecchia CLI sono <code>apps</code>, <code>code_contests</code> e <code>xCodeEval</code>.</td>
      <td>Seleziona il vecchio nome del dataset usato dalla CLI legacy.</td>
    </tr>
    <tr>
      <td><code>eval_code.py</code> legacy</td>
      <td><code>--model_name</code></td>
      <td>No</td>
      <td><code>deepseek-coder-7b-instruct-v1.5</code></td>
      <td>Nome del modello</td>
      <td>Individua la cartella dei risultati da valutare.</td>
    </tr>
    <tr>
      <td><code>eval_code.py</code> legacy</td>
      <td><code>--train</code></td>
      <td>No</td>
      <td>Disattivato</td>
      <td>Flag senza valore</td>
      <td>Seleziona la vecchia partizione di addestramento.</td>
    </tr>
    <tr>
      <td><code>eval_code.py</code> legacy</td>
      <td><code>--test</code></td>
      <td>No</td>
      <td>Disattivato</td>
      <td>Flag senza valore</td>
      <td>Seleziona la vecchia partizione di valutazione. Se non si passa né questo flag né <code>--train</code>, il programma termina senza elaborare dati.</td>
    </tr>
    <tr>
      <td><code>eval_code.py</code> legacy</td>
      <td><code>--debug</code></td>
      <td>No</td>
      <td>Disattivato</td>
      <td>Flag senza valore</td>
      <td>Abilita la diagnostica durante la valutazione.</td>
    </tr>
  </tbody>
</table>

Per vedere la guida generata direttamente da ogni entry point usare questi comandi dopo avere installato le dipendenze.

```powershell
python alignment.py --help
python download_datasets.py --help
python eval_code.py --help
```

## Benchmark disponibili

1. APPS usa l'identificatore `apps`.

2. APPS-Eval usa l'identificatore `apps-eval`.

3. CodeContests-Raw usa l'identificatore `codecontests-raw`.

APPS e APPS-Eval condividono il file `Datasets/apps.jsonl`. È quindi sufficiente scaricarlo una sola volta. CodeContests-Raw usa `Datasets/code_contests.jsonl`.

## Download dei dataset

Il downloader mostra un menu con le sole tre scelte supportate. Inserire il numero del dataset desiderato.

```powershell
python download_datasets.py
```

Per scaricare direttamente APPS usare questo comando.

```powershell
python download_datasets.py --benchmark apps
```

Per scaricare direttamente APPS-Eval usare questo comando. Se APPS è già stato scaricato, il programma riconosce che il file condiviso è presente e non lo scarica di nuovo.

```powershell
python download_datasets.py --benchmark apps-eval
```

Per scaricare direttamente CodeContests-Raw usare questo comando.

```powershell
python download_datasets.py --benchmark codecontests-raw
```

Zenodo distribuisce i dataset in un unico archivio. Il programma scarica l'archivio ufficiale, verifica dimensione e MD5, estrae soltanto il file richiesto e lo verifica tramite dimensione e CRC32. Al termine conserva nella cartella `Datasets` solo il file scelto e rimuove l'archivio temporaneo.

Un dataset valido già presente non viene sovrascritto. Per sostituire volontariamente un file esistente aggiungere `--force`.

```powershell
python download_datasets.py --benchmark apps --force
```

## Avvio della baseline (Base)

La baseline è la modalità predefinita. I comandi seguenti usano DeepSeek e un massimo di 10 iterazioni perché `--model_name`, `--variant` e `--max_iter` non vengono specificati.

### APPS

```powershell
python alignment.py --benchmark apps --save_dir baseline_apps
```

### APPS-Eval

```powershell
python alignment.py --benchmark apps-eval --save_dir baseline_apps_eval
```

### CodeContests-Raw

```powershell
python alignment.py --benchmark codecontests-raw --save_dir baseline_codecontests_raw
```

## Avvio della variante A

La variante `A` attiva il workflow MetaGPT nel Coder Agent. Anche questi comandi usano DeepSeek e un massimo di 10 iterazioni.

### APPS

```powershell
python alignment.py --variant A --benchmark apps --save_dir metagpt_apps
```

### APPS-Eval

```powershell
python alignment.py --variant A --benchmark apps-eval --save_dir metagpt_apps_eval
```

### CodeContests-Raw

```powershell
python alignment.py --variant A --benchmark codecontests-raw --save_dir metagpt_codecontests_raw
```

La variante `A` esegue quattro chiamate al modello per ogni generazione del Coder Agent. Richiede quindi più tempo della baseline. Il modello viene caricato una sola volta.

## Avvio delle varianti B–F

Gli esempi seguenti usano APPS. `apps-eval` e `codecontests-raw` funzionano sostituendo `--benchmark` e il nome di `--save_dir` come negli esempi della variante A.

### Variante B MetaGPT nel Tester Agent

```powershell
python alignment.py --variant B --benchmark apps --save_dir metagpt_tester_apps
```

Il Coder resta diretto. Il Tester esegue quattro chiamate sequenziali: analisi, design, generazione JSON e revisione/validazione.

### Variante C MetaGPT nel Coder e Tester Skill

```powershell
python alignment.py --variant C --benchmark apps --save_dir metagpt_coder_tester_skill_apps
```

Il Coder riusa il workflow A. Il Tester resta un singolo agente, ma riceve `DEFAULT_TESTER_SKILL`.

### Variante D MetaGPT nel Coder e nel Tester

```powershell
python alignment.py --variant D --benchmark apps --save_dir metagpt_both_apps
```

Coder e Tester usano entrambi i rispettivi workflow a quattro ruoli; nessuna Skill viene iniettata.

### Variante E Tester Skill

```powershell
python alignment.py --variant E --benchmark apps --save_dir tester_skill_apps
```

Coder e Tester restano diretti; solo il prompt del Tester viene arricchito dalla Skill.

### Variante F integrazione completa

```powershell
python alignment.py --variant F --benchmark apps --save_dir full_integration_apps
```

Il Coder usa MetaGPT. Il Tester usa MetaGPT e applica la Tester Skill durante analisi, design, generazione e review.

## Esecuzione rapida

Per controllare una configurazione con una sola iterazione usare questo comando.

```powershell
python alignment.py --variant F --benchmark apps --save_dir controllo --max_iter 1
```

## Risultati

I risultati vengono salvati secondo questa struttura.

```text
Results/<modello>/<benchmark>/<save_dir>/
```

Per ogni variante A–F viene aggiunto automaticamente il relativo suffisso al nome indicato in `--save_dir`. Per esempio, il comando APPS della variante A crea la directory seguente.

```text
Results/deepseek-coder-7b-instruct-v1.5/apps/metagpt_apps_A/
```

La console mostra Pass@1 e AvgPassRatio durante l'esecuzione. Se il processo viene interrotto, rilanciare lo stesso comando per riutilizzare gli artefatti già salvati.

Ogni chiamata al modello viene registrata nella directory del run:

- `token_usage.jsonl`: un evento per chiamata, con benchmark, problema, iterazione, fase, agente, token di input, token di output e totale;
- `token_usage_summary.json`: totale del benchmark e aggregazioni per agente, iterazione e fase.

Per ogni problema che richiede test aggiuntivi vengono salvati anche `<problem_id>_test_case` e `<problem_id>_tester_trace.json`. La trace indica workflow, Skill e output intermedi dei ruoli Tester.

> [!note] Nota
> **Come vengono contati i token.** Per i modelli locali, input e output sono calcolati direttamente dagli ID del tokenizer. Per le API vengono letti i valori `usage` restituiti dal provider. Se `usage` non è disponibile, il conteggio viene stimato e l'evento riporta `estimated: true` insieme al metodo usato.
>
> **Effetto della cache.** Quando un risultato già salvato evita una nuova chiamata al modello, non vengono consumati token e non viene creato alcun nuovo evento. Se si riprende lo stesso run, il riepilogo conserva i token delle chiamate eseguite in precedenza, mentre ogni risultato recuperato dalla cache aggiunge zero token.

## Cache dell'Initial Code e parallelismo

La cache dell'Initial Code conserva, per ogni problema, prompt iniziale, codice generato, risultato dei test e trace del Coder. Serve a due scopi:

1. riprendere un'esecuzione senza ripetere chiamate LLM già completate;
2. confrontare varianti che modificano soltanto il Tester usando esattamente lo stesso codice iniziale, evitando variazioni casuali dovute al sampling.

La cache dipende dal modello effettivo, dal benchmark e dal workflow del Coder. `--save_dir` separa i risultati finali, ma non crea una nuova cache dell'Initial Code.

| Cache | Varianti che la condividono | Workflow Coder |
| --- | --- | --- |
| `test` | `base`, `B`, `E` | Coder diretto originale |
| `test_A` | `A`, `C`, `D`, `F` | MetaGPT Coder: Product Manager, Architect, Project Manager, Engineer |

Non copiare o rinominare `test` in `test_A`, o viceversa: contengono codice prodotto da architetture diverse e il confronto sperimentale diventerebbe invalido.

Il programma non applica lock alla cache. Con lo stesso modello effettivo e lo stesso benchmark, eseguire in parallelo al massimo una variante per gruppo:

- un processo scelto da `base/B/E`;
- un processo scelto da `A/C/D/F`.

Combinazioni consigliate includono `A + B`, `A + E`, `C + B`, `D + E` e `F + base`. Varianti dello stesso gruppo, come `B + E` oppure `A + C`, non devono partire insieme mentre la cache condivisa viene generata. Se la cache è già completa e compatibile, possono leggerla in parallelo perché i risultati finali hanno directory distinte.

Per eseguire `A`, `B` ed `E`, usare due fasi:

1. avviare `A` e `B` in parallelo;
2. avviare `E` dopo il completamento di `B`.

Benchmark diversi e modelli effettivi diversi usano directory cache separate e possono essere eseguiti in parallelo, nei limiti di GPU, memoria e rate limit API.

Con OpenRouter, il modello effettivo entra nel namespace dei risultati:

```text
Results/openrouter__<model-slug>__<hash>/<benchmark>/test/
Results/openrouter__<model-slug>__<hash>/<benchmark>/test_A/
```

Ogni Initial Code OpenRouter possiede inoltre un file `.metadata.json`. La cache viene riutilizzata solo quando il modello configurato e quello effettivo coincidono con i metadati. Le vecchie directory generiche `Results/openrouter/...`, che non identificano il modello effettivo, non vengono riutilizzate automaticamente.

## Configurazione completa del run predefinito

Il comando seguente rappresenta un run predefinito su APPS. `--benchmark` e `--save_dir` sono obbligatori e quindi non possiedono un valore predefinito; tutti gli altri flag vengono omessi.

```bash
python alignment.py --benchmark apps --save_dir baseline_apps
```

| Categoria | Impostazione | Valore predefinito | Note |
| --- | --- | --- | --- |
| CLI | Benchmark | Nessuno | Obbligatorio; nell'esempio è `apps`. Valori: `apps`, `apps-eval`, `codecontests-raw`. |
| CLI | Directory risultati | Nessuna | Obbligatoria tramite `--save_dir`; nell'esempio è `baseline_apps`. |
| CLI | Modello | `deepseek-coder-7b-instruct-v1.5` | Caricato dalla directory `LLMs/deepseek-coder-7b-instruct-v1.5/`. |
| CLI | Variante | `base` | Usa il Coder Agent originale con una sola chiamata per ogni generazione di codice. |
| CLI | Iterazioni massime | `10` | Corrisponde a `--max_iter 10`. |
| CLI | Debug | Disattivato | Si abilita aggiungendo `--debug`. |
| Generazione | Token massimi del codice | `1024` | Valore dichiarato nel paper e usato dal Coder Agent. |
| Generazione | Temperatura | `0.8` | Valore dichiarato nel paper. |
| Generazione | Sampling | Attivato | `do_sample=True`, necessario affinché la temperatura venga applicata da Transformers. |
| Generazione | Seed casuale | Non impostato | Due run possono produrre output differenti a causa del sampling. |
| Generazione | Batch | `1` prompt | Il tokenizer riceve un solo prompt per chiamata. |
| Generazione | Padding token | Token EOS del tokenizer | `pad_token_id=tokenizer.eos_token_id`. |
| Generazione | Fine sequenza | Token EOS del tokenizer | `eos_token_id=tokenizer.eos_token_id`. |
| Caricamento | Precisione dei pesi | Automatica | `torch_dtype="auto"` conserva la precisione indicata dal checkpoint. |
| Caricamento | Posizionamento | Automatico | `device_map="auto"` distribuisce il modello sulle risorse disponibili. |
| Fasi Specine | Lifting della specifica | Massimo `512` token | Limite specifico della fase interna. |
| Fasi Specine | Selezione del disallineamento | Massimo `64` token | Limite specifico della fase interna. |
| Fasi Specine | Regola di allineamento | Massimo `256` token | Limite specifico della fase interna. |
| Fasi Specine | Generazione test aggiuntivi | Massimo `1024` token | Usata quando servono test generati dal modello. |
| Tester MetaGPT | Test Analyst e Test Designer | Massimo `512` token per ruolo | Fasi intermedie delle varianti B, D e F. |
| Tester MetaGPT | Test Generator e Test Reviewer / Validator | Massimo `1024` token per ruolo | Generazione e correzione del JSON finale. |
| Output | Percorso risultati | `Results/<modello>/<benchmark>/<save_dir>/` | Per A–F viene aggiunto automaticamente il suffisso della variante. |
| Output | Consumo token | Registrazione automatica | Salva ogni chiamata LLM e aggrega input/output per agente, iterazione e fase. |

I valori `max tokens = 1024`, `temperature = 0.8` e `N = 10` seguono la sezione 4.4 del [paper di Specine](https://arxiv.org/pdf/2509.01313). La variante `A` mantiene la configurazione originale già implementata: Product Manager, Architect e Project Manager hanno limite 512 token; Engineer conserva 1024 token. Le varianti B–F compongono i tre moduli senza modificare il processo comune di lifting e alignment.
