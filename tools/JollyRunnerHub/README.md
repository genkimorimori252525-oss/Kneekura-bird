# ジョリー Runner Hub

Windowsの自己ホストGitHub Actions Runnerをデスクトップから起動・停止し、GameTestが出力するJSONLテレメトリをリアルタイムで可視化する軽量WinFormsアプリです。

## 主な機能

- 起動時にWindowsへ管理者権限を要求
- 選択したRunnerの自動接続、接続、切断
- RunnerプロセスとRunnerログを組み合わせたGitHub接続状態の判定
- 複数リポジトリのプロファイル管理
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

ヘッダーのRunner表示は、`Runner.Listener.exe`の存在だけではなく、HubログとActions Runnerの最新 `_diag/Runner_*.log` を時系列で読み、最後の接続マーカーから判定します。

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
7. ヘッダー・タブ・6グラフを含む全UIの非表示起動スモークテスト
8. `%LOCALAPPDATA%\JollyRunnerHub` とデスクトップへ配置

追加ランタイムは不要です。GUI本体はWindows PowerShell 5.1 + WinForms + .NET Framework標準Chartingで動作します。
