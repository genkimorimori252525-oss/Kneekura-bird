# ジョリー Runner Hub

Windowsの自己ホストGitHub Actions Runnerを、デスクトップのアプリから起動・停止し、GameTestが出力するJSONLテレメトリをリアルタイム表示する軽量ツールです。

## 主な機能

- 起動時にWindowsへ管理者権限を要求
- 選択したRunnerの自動接続、接続、切断
- 複数リポジトリのプロファイル管理
- 検証中はJSONLを1秒ごとに読み込み
- 検証停止中は表示値を0またはIDLEへ戻す
- 機体別メトリクス、最新イベント、Runnerログを表示
- `profiles.json` の `metrics` 配列を編集するだけで表示項目を追加可能

## 設定場所

`%LOCALAPPDATA%\JollyRunnerHub\profiles.json`

### metricの指定

- `source`: `frame` / `event` / `coupled` / `reason`
- `path`: JSONプロパティ名、またはreason内の `key=value` のkey
- `format`: 数値書式。例 `0.00`
- `default`: 検証停止時または値欠損時の表示

別リポジトリはアプリ上部の「追加」から登録できます。テレメトリ項目を増やす場合は「設定JSON」を開き、対象プロファイルの`metrics`へ追加してください。

## ビルドと配置

`Build-Deploy.ps1` はWindows標準の.NET Frameworkコンパイラを使用し、追加ランタイムなしの小さなランチャーEXEを生成します。GUI本体はWindows PowerShell + WinFormsで動作します。
