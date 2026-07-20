# AirplaneAutopilot.java バグレポート

ファイル: `Airforce/source_repo/common/src/main/java/immersive_aircraft/entity/ai/AirplaneAutopilot.java`
総行数: ~3,982行

---

## BUG #1: ブレーキ不能 [CRITICAL]

**場所**: Lines 1771, 1695, 1779

**問題**: autopilotは**負のスロットル入力を送れない**ため、ブレーキが一切効かない。

**メカニズム**:
```java
// Line 1771 (applyGroundOperationOutput)
float throttleError = output.throttle() - plane.getEngineTarget();
float throttleInput = throttleError > 0.06f ? 1.0f : throttleError < -0.06f ? -1.0f : 0.0f;
```

- AirplaneEntityではブレーキは `movementY < 0` のとき**のみ**発動（velocity *= 0.95）
- PARKING/SHUTDOWN時: desiredThrottle=0.0, engineTarget≈0.05 → error=-0.05
- **-0.05 は -0.06 より大きい** → throttleInput=0.0 → ブレーキ不発動
- 結果: 着陸後に止まれない、地上でスライドし続ける

**修正方針**:
- ブレーキ閾値を -0.04f に変更
- または着陸状態で明示的にthrottleInput=-1.0fを送る

---

## BUG #2: エンジン始動の間接性 [HIGH]

**場所**: Lines 670-675, 613, 1694-1696

**問題**: エンジンは直接 `setEngineTarget()` ではなく、スロットル入力経由で間接的に始動。

**メカニズム**:
```java
// Line 670-675 (STARTUP → TAXI_OUT 遷移条件)
if (plane.getEngineTarget() >= 0.95f
        && operationStateTicks > 18
        && (launchGroupReady(...) || operationStateTicks > 65)) {
    yield OperationState.TAXI_OUT;
}
```

- STARTUP状態でthrottleInput=1.0を送る → engineTarget += 0.1/tick
- 理論上10tickで1.0に到達するが、入力補間の遅延あり
- 65tickタイムアウトでTAXI_OUTに強制遷移 → エンジンが不完全な状態で出発の可能性

**修正方針**:
- STARTUP開始時に `plane.setEngineTarget(1.0f)` を直接呼ぶ
- またはタイムアウト後もエンジンチェックを継続

---

## BUG #3: 着陸ループ (APPROACH ↔ FINAL) [HIGH]

**場所**: Lines 728-748, 942-943

**問題**: FINAL状態が80tick超でAPPROACHに戻り、APPROACHが即座にFINALに戻る無限ループ。

**メカニズム**:
```java
// Line 744-745 (FINAL → APPROACH ループ)
if (operationStateTicks > 80 && context.altitudeAboveGround() > context.profile().safeAltitude()) {
    yield OperationState.APPROACH;
}

// Line 942-943 (shouldEnterFinal)
return horizontalDistance(...) < Math.max(14.0, ...) || operationStateTicks > 40;
```

- FINAL → 80tick超 + 高度高い → APPROACH
- APPROACH → 距離近いOR 40tick超 → FINAL
- 降下が間に合わないと永久にループ

**修正方針**:
- FINALからAPPROACHに戻るとき、再進入角度を強制
- 前進距離に基づく進捗チェック追加

---

## BUG #4: 武器射程チェックなし [MEDIUM]

**場所**: Lines 1807-1821

**問題**: 発射判定が角度のみ（17.3°以内）で、距離チェックがない。

```java
// 発射条件: 角度チェックのみ
mountForward.dot(desiredDirection.normalize()) >= 0.955f  // ~17.3度
```

- 100ブロック先の敵にも発射 → 弾浪費
- 特に機銃は有効射程が限られるはず

**修正方針**: 武器タイプ別の最大射程チェックを追加
- 機銃: 40-60ブロック
- 爆弾: 高度基準

---

## BUG #5: アプローチ中の失速未対策 [MEDIUM]

**場所**: アプローチスロットル設定部

**問題**: アプローチスロットル0.62fが全機体共通。重い機体（B-17: mass=18.0）は失速する可能性。

**修正方針**: 機体質量に応じたスロットル下限
- `minApproachThrottle = 0.4f + mass * 0.02f` のような計算

---

## BUG #6: 離陸時の速度チェック欠如 [MEDIUM]

**場所**: Line 685

```java
case TAKEOFF_ROLL -> !context.onGround() ? OperationState.ROTATE : OperationState.TAKEOFF_ROLL;
```

**問題**: 地面を離れた瞬間にROTATEに遷移。速度が不十分でも離陸を試みる。

**修正方針**: `context.speed() > stallSpeed * 1.3` のチェック追加

---

## 燃料・武器システム確認結果

### 燃料無効化
- `Config.fuelConsumption = 0` → `getFuelUtilization()` が 1.0f を返す (Line 284-286)
- エンジン始動条件 `getFuelUtilization() > 0` を通過 (Line 270-282)
- **確認済み: 設定変更のみでAI機の燃料問題は解決**

### 武器自動装備
- `onPilotMounted()` → `autoSupplyLoadout()` → `autoSupplyWeapons()` (Lines 219-253)
- Warfare Wings固有の武器参照あり: `"warfare_wings:wing_mg"` (Line 43)
- 機種別選択ロジック:
  - FIGHTER: FRONT優先 → warfare_wings:wing_mg
  - ATTACKER: FRONT優先 → DROP
  - BOMBER/TORPEDO_BOMBER: DROP優先 → faction別爆弾
- 陣営別爆弾: IJN→ww_jbomb, LUFTWAFFE→ww_gbomb, VVS→ww_sbomb, USAAF→ww_bomb
- **確認済み: パイロット搭乗時に自動装備される**

### 燃料自動補給
- `autoSupplyFuel()`: 空のboilerスロットに石炭32個 (Lines 233-241)
- fuelConsumption=0なら消費されない
