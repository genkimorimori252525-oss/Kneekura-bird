# ジョリー Runner Hub

Windowsの自己ホストGitHub Actions Runnerをデスクトップから起動・停止し、GameTestが出力するJSONLテレメトリをリアルタイムで可視化する軽量WinFormsアプリです。

## 主な機能

- 起動時にWindowsへ管理者権限を要求
- 選択したRunnerの自動接続、接続、切断
- 複数リポジトリのプロファイル管理
- 1秒ごとにJSONLテレメトリを読み込み
- 機体ごとの現在値カード
  - Phase / Stage
  - Speed
  - AGL
  - Separation
  - Stall / Terrain / Ground状態
- 表示メトリクスを選べる2枚のリアルタイム折れ線グラフ
- 全メトリクスの詳細表
- 最新イベント一覧とRunnerログ
- 実行履歴を `%LOCALAPPDATA%\JollyRunnerHub\history` へ自動保存
- 保存済み実行を選び、任意の数値メトリクスをグラフと表で再表示
- Separationを選択したグラフには安全下限8ブロックを表示
- 検証停止中も直前のグラフを保持し、現在値カードと詳細表はIDLEへ戻す
- `profiles.json` の `metrics` 配列だけで表示項目を追加可能

## 画面構成

### ダッシュボード

上段に機体ごとの状態カード、中段に2枚のリアルタイムグラフ、下段に全メトリクスの詳細表を表示します。グラフ右上のプルダウンからSpeed、AGL、Pitch、Roll、Separationなどを切り替えられます。

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

1. `JollyRunnerHub.ps1` のPowerShell構文検証
2. Chartingアセンブリの存在確認
3. `profiles.default.json` のJSON検証
4. Windows標準の.NET FrameworkコンパイラでランチャーEXEを生成
5. `%LOCALAPPDATA%\JollyRunnerHub` とデスクトップへ配置

追加ランタイムは不要です。GUI本体はWindows PowerShell 5.1 + WinForms + .NET Framework標準Chartingで動作します。
