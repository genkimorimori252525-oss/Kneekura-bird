# ジョリー Runner Hub

Windowsの自己ホストGitHub Actions Runnerをデスクトップから起動・停止し、GameTestが出力するJSONLテレメトリをリアルタイムで可視化する軽量WinFormsアプリです。

## 主な機能

- 起動時にWindowsへ管理者権限を要求
- 登録済みRunnerの一括自動接続、個別/一括の起動と停止
- RunnerプロセスとRunnerログを組み合わせたGitHub接続状態の判定
- `Runner 管理` タブで複数リポジトリの状態、配置先、判定根拠を一覧表示
- `%LOCALAPPDATA%\GitHubActions` と `C:\actions-runner*` を監査し、profileにもHub Ephemeral領域にも属さないRunnerを`未管理`として警告表示
- 未管理Runnerは自動起動・停止・復旧の対象にせず、勝手に削除もしない
- Warfare Wings、Love-Github、KNEEKURA LAB、KNEEKURA CODE-LAB、Durable Workflowの独立したrepo-scoped Runnerプロファイル
- 1秒ごとにJSONLテレメトリを読み込み
- 実行中のテレメトリから機体名を自動検出
- 検証終了後は直近の保存履歴から機体名を復元
- 機体ごとの現在値カード
  - Phase / Stage
  - Speed
  - AGL
  - Separation
  - Stall / Terrain / Ground状態
- 表示メトリクスを個別に選べる6枚のリアルタイム折れ線グラフ
  - 既定: Speed / AGL / Pitch / Roll / Separation / Control X
- 全メトリクスの詳細表
- 最新イベント一覧とRunnerログ
- 実行履歴を `%LOCALAPPDATA%\JollyRunnerHub\history` へ自動保存
- 保存済み実行を選び、任意の数値メトリクスをグラフと表で再表示
- Separationを選択したグラフには安全下限8ブロックを表示
- 検証停止中も直前のグラフを保持
- `profiles.json` の `metrics` 配列だけで表示項目を追加可能

## Runner状態の意味

ヘッダーと`Runner 管理`タブの表示は、Hubが記録した起動プロセス、使用中の最新 `_diag/Runner_*.log`、Hubログを組み合わせ、最後の接続マーカーから判定します。Windowsがプロセスの実行パスを返さない場合も、Runnerごとの診断ログのファイルロックで二重起動を防ぎます。

- `停止中`: `Runner.Listener.exe`が存在しない。
- `起動中（接続確認待ち）`: プロセスは存在するが、GitHub接続を示すログがまだない。
- `接続中（待機準備）`: GitHubセッション確立までは確認できたが、ジョブ待機開始はまだ確認できない。
- `待機中（GitHub接続）`: `Listening for Jobs`を確認済み。GitHubからジョブを受け取れる状態。
- `実行中（GitHub接続）`: `Running job:`を確認済み。
- `接続確認中`: ジョブ終了直後など、次の待機マーカーを確認している状態。
- `再接続中`: セッション作成失敗、切断、名前解決失敗、タイムアウトなどが最後の接続マーカーになっている。

黄色表示は「プロセスはいるがGitHub待機を証明できない」状態です。従来のようにプロセスが存在するだけで一律に`接続中`とは表示しません。

接続判定は表示補助です。実際の検証受理は、対象workflowのRun IDとリポジトリの検証状態ファイルで確認してください。

## 画面構成

### Runner 管理

5つの正式Runner profileを同時に表示し、選択した管理Runnerまたは登録済みRunner全体を起動・停止できます。停止はHubが起動元プロセスを記録して安全に対象を特定できる場合だけ実行します。

- Warfare Wings: `C:\actions-runner`
- Love-Github: `C:\actions-runner-love-github`
- KNEEKURA LAB: `C:\actions-runner-kneekura-lab`
- KNEEKURA CODE-LAB: `C:\actions-runner-kneekura-code-lab`
- Durable Workflow: `C:\actions-runner-durable-workflow`

`%LOCALAPPDATA%\GitHubActions\*` などに手作業で作った `Once-*` Runnerは`未管理`として別表示されます。今後の一時Runnerは`Ephemeral起動`から作成し、恒久Runnerが必要なrepositoryは`profiles.json`へ正式profileを追加します。この二択にすることで、Hubの管轄外Runnerが増殖するのを防ぎます。

各personal repositoryのRunner資格情報は共有せず、それぞれのディレクトリに独立して保持します。`profiles.json`にはrunner tokenやcredentialを保存しません。

### CI routing

各workflowは登録先repositoryと一致するcustom labelを使用します。

- Love-Github: `love-github`
- KNEEKURA LAB: `kneekura`
- KNEEKURA CODE-LAB: `kneekura-code-lab`
- Durable Workflow: `durable-workflow`

workflowの`runs-on`を変更した場合は、古いrunを再実行せず、変更後のcommitから新規runを発生させます。GitHub Actionsの再実行は元runのcommitとworkflow定義を使用するため、GitHub-hosted runner向けの古いrunはself-hosted検証になりません。

Windows PowerShell 5.1が必要なstepは`shell: powershell`を明示します。`pwsh`を使用するstepは、対象RunnerにPowerShell 7がインストールされPATHから解決できることを事前に確認します。

`autoConnect: true`では、Hub起動時に登録済みの全Runnerを接続します。すでに動作中のRunnerは診断ログの使用状態も含めて検出し、重複起動しません。

### 更新時のUI安定性

Runner一覧は行を毎回破棄して作り直さず、Runner IDをキーに差分更新します。選択行とスクロール位置を保持し、Runner管理タブを開いている時だけ3秒間隔で一覧を更新します。能力情報はsnapshotを1回だけ読み、ログ表示もRunnerログタブを開いている時だけ2秒間隔で差分更新します。

アプリ終了時には選択profile、選択タブ、Runner選択を `%LOCALAPPDATA%\JollyRunnerHub\ui-state.json` へ保存します。JollyRunnerHub本体を更新して再起動しても、作業していた画面へ戻れます。

### Ephemeral Runner lifecycle

`Manage-EphemeralRunner.ps1` は、検証専用のrepo-scoped Runnerを常設Runnerとは別のrootへ生成します。

```powershell
& "$env:LOCALAPPDATA\JollyRunnerHub\Manage-EphemeralRunner.ps1" `
  -Command spawn `
  -Repository 'owner/repository' `
  -Labels @('validation-only') `
  -SourceRunnerRoot 'C:\actions-runner-love-github' `
  -TtlMinutes 60
```

- GitHub registration tokenはstateやログへ保存せず、`config.cmd`実行中のprocess environmentだけで使用します。
- instanceごとに固有のRunner名、runner root、`_work`を使用します。
- watchdogは`RUNNER_TRACKING_ID`を継承せず、親Actions job終了後も割当済みjobを完走できます。
- job終了またはTTL到達後、GitHub登録解除とrunner root清掃を行います。
- `status`、`stop`、`gc`はinstance IDを対象とし、ephemeral base外のpathを削除しません。
- `%LOCALAPPDATA%\JollyRunnerHub\ephemeral\<instance>\state.json`にはtokenやcredentialを含めません。

### Runner能力

`Runner 管理`タブの`能力を更新`は、Git、GitHub CLI、Node、Java/Javac、Gradle、Python、Docker/Linux engine、WSL、通常Ubuntu distro、Actions tool cacheを個別に検査します。結果は`ready / degraded / unavailable`と根拠に分けて`%LOCALAPPDATA%\JollyRunnerHub\capabilities.json`へ保存します。各Profileの`requiredCapabilities`に対する充足数と不足項目が画面に表示されます。

```powershell
& "$env:LOCALAPPDATA\JollyRunnerHub\Inspect-RunnerCapabilities.ps1" `
  -RunnerRoots @('C:\actions-runner-love-github','C:\actions-runner-durable-workflow') `
  -OutputPath "$env:LOCALAPPDATA\JollyRunnerHub\capabilities.json"
```

Self-hosted CIは`Use-LocalGradle.ps1`で固定済みGradle distributionを有効化します。Gradle 8.8がローカルcacheにない場合は、network downloadを開始せず`TOOLCHAIN_FAILURE`として即時終了します。

### ダッシュボード

ヘッダー、機体カード、6枚のミニグラフ、詳細表を重ならない固定レイアウト行に分けて表示します。各グラフのプルダウンからSpeed、AGL、Pitch、Roll、Separationなどを切り替えられます。

機体カードと系列名は `expectedAircraft` の固定値ではなく、実行中のJSONLにある `aircraft_name` を優先します。そのため、A6M・P-47N以外の検証でも同じアプリをそのまま使用できます。待機中は直近のローカル履歴に含まれる機体名を表示し、まだ一度も履歴がない場合は機体カードを空にします。

### 履歴

アプリが検証中の最新値を1秒単位でローカルJSONLへ保存します。GitHub Actionsのワークスペースが清掃された後も、履歴タブから過去の実行を確認できます。

既定値:

- 保存期間: 30日
- 最大保存実行数: 100

プロファイルの `historyDays` と `historyMaxRuns` で変更できます。

### イベント / Runnerログ

GameTestのイベントとRunnerプロセスのログを別タブで確認できます。

## 設定場所

`%LOCALAPPDATA%\JollyRunnerHub\profiles.json`

### metricの指定

- `key`: アプリ内で使用する一意な名前
- `label`: 表とグラフに表示する名前
- `source`: `frame` / `event` / `coupled` / `reason`
- `path`: JSONプロパティ名、またはreason内の `key=value` のkey
- `format`: 数値書式。例 `0.00`
- `default`: 検証停止時または値欠損時の表示

`format`を持つメトリクスは、原則としてグラフ選択肢にも表示されます。

## ビルドと配置

`Build-Deploy.ps1` は次を実行します。

1. `JollyRunnerHub.ps1` と `RunnerConnectionState.ps1` のPowerShell構文検証
2. 接続状態分類器の停止・起動・接続準備・待機・実行・再接続サンプルテスト
3. Chartingアセンブリの存在確認
4. `profiles.default.json` のJSON検証
5. Windows標準の.NET FrameworkコンパイラでランチャーEXEを生成
6. 接続状態分類器を含む実行時スクリプトの構文検証
7. Runner管理、接続判定、チャートを含む実行時sourceの構文・必須パッチassertion
8. `%LOCALAPPDATA%\JollyRunnerHub` とデスクトップへ配置

追加ランタイムは不要です。GUI本体はWindows PowerShell 5.1 + WinForms + .NET Framework標準Chartingで動作します。


## Ephemeral Runner / capability 管理

- Runner 管理タブから、選択したrepo profile用の独立Ephemeral Runnerを明示操作で作成できます。常設Runnerの資格情報はコピーせず、runner binaryだけを隔離ディレクトリへ複製し、GitHubの短寿命registration tokenで `--ephemeral` 登録します。
- Ephemeral Runnerは既定30分、最小5分・最大120分のTTLを持ちます。TTL切れでもGitHubが `busy=true` のjobは強制停止しません。GitHub状態を確認できない場合もfail-safeで保持します。
- Hubは30秒ごとと手動 `Ephemeral GC` で終了済み/期限切れstateを回収します。削除対象は `%LOCALAPPDATA%\JollyRunnerHub\ephemeral` 配下とHubが記録したprocess IDに限定します。
- `Capabilities` 列はrunner files / git / gh / Docker / WSL / Python / PowerShell 7 / Javaをキャッシュ付きで表示します。`Ephemeral / TTL` 列はprofileごとのactive/expired/GC pendingを表示します。
- 自動起動は従来どおり常設Runnerだけです。Ephemeral Runnerはユーザーまたは検証フローの明示操作なしには作成しません。
