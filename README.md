# Specine con Coder MetaGPT

## Obiettivo

Questo fork confronta la generazione originale di Specine con una variante che inserisce un workflow ispirato a MetaGPT nel Coder Agent.

La baseline usa una singola chiamata al modello per generare il codice. La variante `A` usa in sequenza Product Manager, Architect, Project Manager ed Engineer. Gli altri componenti di Specine restano invariati.

I benchmark disponibili sono esclusivamente APPS, APPS-Eval e CodeContests-Raw.

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

Dopo avere installato le dipendenze, scaricare il modello con questo comando.

```powershell
huggingface-cli download deepseek-ai/deepseek-coder-7b-instruct-v1.5 --local-dir LLMs/deepseek-coder-7b-instruct-v1.5
```

In alternativa, scaricare manualmente `deepseek-ai/deepseek-coder-7b-instruct-v1.5` da Hugging Face e collocarlo in questa posizione.

```text
LLMs/deepseek-coder-7b-instruct-v1.5/
```

La directory deve contenere configurazione, tokenizer e pesi del modello.

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
      <td><code>deepseek-coder-7b-instruct-v1.5</code>, <code>Qwen2.5-Coder-7B-Instruct</code>, <code>gpt-4o-mini-2024-07-18</code>, <code>gemini-1.5-flash-002</code></td>
      <td>Seleziona il modello locale o il backend API.</td>
    </tr>
    <tr>
      <td><code>alignment.py</code></td>
      <td><code>--variant</code></td>
      <td>No</td>
      <td><code>base</code></td>
      <td><code>base</code>, <code>A</code>, <code>B</code>, <code>C</code></td>
      <td><code>base</code> usa Specine originale. <code>A</code> usa il Coder MetaGPT. <code>B</code> e <code>C</code> sono riservate e al momento terminano con un errore.</td>
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

## Avvio della baseline

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

## Esecuzione rapida

Per controllare la configurazione con una sola iterazione usare questo comando.

```powershell
python alignment.py --variant A --benchmark apps --save_dir controllo --max_iter 1
```

## Risultati

I risultati vengono salvati secondo questa struttura.

```text
Results/<modello>/<benchmark>/<save_dir>/
```

Per la variante `A` il suffisso `_A` viene aggiunto automaticamente al nome indicato in `--save_dir`. Per esempio, il comando APPS della variante crea la directory seguente.

```text
Results/deepseek-coder-7b-instruct-v1.5/apps/metagpt_apps_A/
```

La console mostra Pass@1 e AvgPassRatio durante l'esecuzione. Se il processo viene interrotto, rilanciare lo stesso comando per riutilizzare gli artefatti già salvati.

## Problemi comuni

### Dataset mancante

Eseguire il downloader con lo stesso identificatore usato per il benchmark.

```powershell
python download_datasets.py --benchmark apps
```

### Modello DeepSeek non trovato

Controllare che esista `LLMs/deepseek-coder-7b-instruct-v1.5/` e che la directory contenga tutti i file scaricati da Hugging Face.

### Memoria GPU insufficiente

Chiudere gli altri processi che usano la GPU oppure configurare uno dei backend API supportati in `model.py`.
