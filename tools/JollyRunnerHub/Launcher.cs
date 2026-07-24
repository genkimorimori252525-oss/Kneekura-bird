using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows.Forms;

namespace JollyRunnerHubLauncher
{
    internal static class Program
    {
        private static string ReplaceRequired(
            string source,
            string oldValue,
            string newValue,
            string description)
        {
            if (!source.Contains(oldValue))
            {
                throw new InvalidOperationException(
                    "Runner Hub runtime patch target was not found: " + description);
            }
            return source.Replace(oldValue, newValue);
        }

        private static string ReplaceRegexRequired(
            string source,
            string pattern,
            string replacement,
            string description)
        {
            Regex regex = new Regex(pattern, RegexOptions.Singleline);
            if (!regex.IsMatch(source))
            {
                throw new InvalidOperationException(
                    "Runner Hub runtime patch target was not found: " + description);
            }
            return regex.Replace(source, _ => replacement, 1);
        }

        [STAThread]
        private static void Main(string[] args)
        {
            bool smokeTest = Array.Exists(
                args ?? new string[0],
                arg => string.Equals(arg, "--smoke-test", StringComparison.OrdinalIgnoreCase));

            string appRoot = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "JollyRunnerHub");
            string errorLog = Path.Combine(appRoot, "startup-error.log");

            try
            {
                string sourceOverride = Environment.GetEnvironmentVariable("JOLLY_RUNNER_HUB_SOURCE");
                string sourceScript = string.IsNullOrWhiteSpace(sourceOverride)
                    ? Path.Combine(appRoot, "JollyRunnerHub.ps1")
                    : sourceOverride;
                string runtimeScript = Path.Combine(appRoot, "JollyRunnerHub.runtime.ps1");
                string bootstrapScript = Path.Combine(appRoot, "JollyRunnerHub.bootstrap.ps1");

                if (!File.Exists(sourceScript))
                {
                    throw new FileNotFoundException(
                        "アプリ本体が見つかりません。GitHub Actions の Deploy Jolly Runner Hub を再実行してください。",
                        sourceScript);
                }

                Directory.CreateDirectory(appRoot);
                string scriptText = File.ReadAllText(sourceScript)
                    .Replace("\r\n", "\n");

                // Windows PowerShell functions emit every uncaptured expression. Controls.Add and
                // List.Add return integers, which can turn the intended return value into Object[].
                scriptText = scriptText
                    .Replace("$top.Controls.Add($b);return $b", "[void]$top.Controls.Add($b);return $b")
                    .Replace("$lines.Add($line)", "[void]$lines.Add($line)")
                    .Replace("$rows.Add(($line | ConvertFrom-Json))", "[void]$rows.Add(($line | ConvertFrom-Json))")
                    .Replace("$aircraft.Add([pscustomobject]", "[void]$aircraft.Add([pscustomobject]")
                    .Replace("$planes.Add([pscustomobject]", "[void]$planes.Add([pscustomobject]")
                    .Replace("$events.Add([pscustomobject]", "[void]$events.Add([pscustomobject]")
                    .Replace("$cells.Add([string]$a.Name)", "[void]$cells.Add([string]$a.Name)")
                    .Replace("{$cells.Add($a.Values[[string]$m.key])}", "{[void]$cells.Add($a.Values[[string]$m.key])}");

                // Windows PowerShell 5.1 can throw "Argument types do not match" when @(...)
                // wraps a generic List<object>. Enumerate those lists directly.
                scriptText = scriptText
                    .Replace("foreach ($a in @($Snapshot.Aircraft))", "foreach ($a in $Snapshot.Aircraft)")
                    .Replace("foreach ($e in @($Snapshot.Events))", "foreach ($e in $Snapshot.Events)")
                    .Replace("foreach ($aircraft in @($Snapshot.Aircraft))", "foreach ($aircraft in $Snapshot.Aircraft)")
                    .Replace("foreach ($event in @($Snapshot.Events))", "foreach ($event in $Snapshot.Events)")
                    .Replace("$grouped = @($Records) | Group-Object aircraft", "$grouped = $Records | Group-Object aircraft");

                // New-Object treats unparenthesized arithmetic in constructor arguments as a string.
                scriptText = scriptText
                    .Replace(
                        "New-Object Drawing.Size($Width-20,14)",
                        "New-Object Drawing.Size(($Width - 20),14)")
                    .Replace(
                        "New-Object Drawing.Size($Width-20,20)",
                        "New-Object Drawing.Size(($Width - 20),20)");

                // Put the header and tabs in separate layout rows. The old BringToFront approach
                // overlaid the first aircraft-card row beneath the header.
                const string rootLayout = @"$rootLayout = New-Object Windows.Forms.TableLayoutPanel
$rootLayout.Dock = 'Fill'
$rootLayout.RowCount = 2
$rootLayout.ColumnCount = 1
$rootLayout.Margin = New-Object Windows.Forms.Padding(0)
$rootLayout.Padding = New-Object Windows.Forms.Padding(0)
[void]$rootLayout.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',116)))
[void]$rootLayout.RowStyles.Add((New-Object Windows.Forms.RowStyle('Percent',100)))
[void]$rootLayout.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle('Percent',100)))
[void]$form.Controls.Add($rootLayout)
$header.Dock = 'Fill'
[void]$rootLayout.Controls.Add($header,0,0)";
                scriptText = ReplaceRequired(
                    scriptText,
                    "$form.Controls.Add($header)",
                    rootLayout,
                    "root header layout");
                scriptText = ReplaceRegexRequired(
                    scriptText,
                    @"\$form\.Controls\.Add\(\$tabs\)\s*\n\$header\.BringToFront\(\)",
                    "[void]$rootLayout.Controls.Add($tabs,0,1)",
                    "tabs below header");

                // Use more of the screen for simultaneous charts while keeping cards and details visible.
                scriptText = scriptText
                    .Replace(
                        "[void]$dashboardLayout.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',144)))",
                        "[void]$dashboardLayout.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',142)))")
                    .Replace(
                        "[void]$dashboardLayout.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',188)))",
                        "[void]$dashboardLayout.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',152)))");

                const string chartGrid = @"$chartGrid = New-Object Windows.Forms.TableLayoutPanel
$chartGrid.Dock = 'Fill'
$chartGrid.ColumnCount = 3
$chartGrid.RowCount = 2
$chartGrid.Padding = New-Object Windows.Forms.Padding(0,0,0,6)
for ([int]$i=0; $i -lt 3; $i++) {
    [void]$chartGrid.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle('Percent',33.3333)))
}
for ([int]$i=0; $i -lt 2; $i++) {
    [void]$chartGrid.RowStyles.Add((New-Object Windows.Forms.RowStyle('Percent',50)))
}
$dashboardLayout.Controls.Add($chartGrid,0,1)

function New-ChartBox([string]$Caption,[string]$PreferredMetric) {
    $box = New-Object Windows.Forms.TableLayoutPanel
    $box.Dock = 'Fill'
    $box.RowCount = 2
    $box.ColumnCount = 1
    $box.Margin = New-Object Windows.Forms.Padding(4)
    $box.BackColor = $ColorSurface
    [void]$box.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',31)))
    [void]$box.RowStyles.Add((New-Object Windows.Forms.RowStyle('Percent',100)))

    $bar = New-Object Windows.Forms.Panel
    $bar.Dock = 'Fill'
    $bar.BackColor = $ColorSurface
    [void]$box.Controls.Add($bar,0,0)

    $label = New-Object Windows.Forms.Label
    $label.Text = $Caption
    $label.Font = New-Object Drawing.Font('Segoe UI',8.5,[Drawing.FontStyle]::Bold)
    $label.ForeColor = $ColorText
    $label.Location = New-Object Drawing.Point(8,7)
    $label.Size = New-Object Drawing.Size(92,20)
    [void]$bar.Controls.Add($label)

    $combo = New-Object Windows.Forms.ComboBox
    $combo.DropDownStyle = 'DropDownList'
    $combo.Anchor = 'Top,Right'
    $combo.Width = 145
    $combo.Location = New-Object Drawing.Point(($bar.Width - 153),4)
    $bar.add_Resize({
        $combo.Location = New-Object Drawing.Point(([math]::Max(104,$bar.ClientSize.Width - 153)),4)
    }.GetNewClosure())
    [void]$bar.Controls.Add($combo)

    $chart = New-Chart
    [void]$box.Controls.Add($chart,0,1)
    return [pscustomobject]@{
        Box=$box
        Combo=$combo
        Chart=$chart
        Preferred=$PreferredMetric
    }
}

$script:ChartBoxes = New-Object System.Collections.Generic.List[object]
[void]$script:ChartBoxes.Add((New-ChartBox '速度' 'speed'))
[void]$script:ChartBoxes.Add((New-ChartBox '高度' 'agl'))
[void]$script:ChartBoxes.Add((New-ChartBox 'ピッチ' 'pitch'))
[void]$script:ChartBoxes.Add((New-ChartBox 'ロール' 'roll'))
[void]$script:ChartBoxes.Add((New-ChartBox '機体間分離' 'separation'))
[void]$script:ChartBoxes.Add((New-ChartBox '操舵入力' 'control_x'))
for ([int]$i=0; $i -lt $script:ChartBoxes.Count; $i++) {
    [int]$column = $i % 3
    [int]$row = [math]::Floor($i / 3)
    [void]$chartGrid.Controls.Add($script:ChartBoxes[$i].Box,$column,$row)
}";
                scriptText = ReplaceRegexRequired(
                    scriptText,
                    @"\$chartGrid = New-Object Windows\.Forms\.TableLayoutPanel.*?\$chartGrid\.Controls\.Add\(\$chartBBox\.Box,1,0\)",
                    chartGrid,
                    "six-chart dashboard grid");

                // During an active validation, names already come from aircraft_name in telemetry.
                // While idle, show the latest locally persisted run instead of hard-coded A6M/P-47N.
                const string dynamicIdleNames = @"$names = New-Object System.Collections.Generic.List[string]
foreach ($sampleName in ($script:LiveSamples | Select-Object -ExpandProperty aircraft -Unique)) {
    if (-not [string]::IsNullOrWhiteSpace([string]$sampleName)) {
        [void]$names.Add([string]$sampleName)
    }
}
if ($names.Count -eq 0) {
    try {
        $latestHistory = Get-ChildItem -LiteralPath (History-ProfileRoot $Profile) -Filter '*.jsonl' -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First 1
        if ($null -ne $latestHistory) {
            foreach ($sampleName in (Read-History $latestHistory.FullName | Select-Object -ExpandProperty aircraft -Unique)) {
                if (-not [string]::IsNullOrWhiteSpace([string]$sampleName)) {
                    [void]$names.Add([string]$sampleName)
                }
            }
        }
    } catch {}
}
if ($names.Count -eq 0) {
    return [pscustomobject]@{
        Active = $false
        Run = 'IDLE'
        Updated = $null
        Aircraft = @()
        Events = @()
    }
}";
                scriptText = ReplaceRequired(
                    scriptText,
                    "$names = @($Profile.expectedAircraft)\n    if ($names.Count -eq 0) { $names = @('Aircraft') }",
                    dynamicIdleNames,
                    "dynamic idle aircraft names");

                const string selectProfileCharts = @"foreach ($chartBox in $script:ChartBoxes) {
        Fill-MetricCombo $chartBox.Combo $script:Profile ([string]$chartBox.Preferred)
    }
    Fill-MetricCombo $historyMetric $script:Profile 'speed'";
                scriptText = ReplaceRequired(
                    scriptText,
                    "Fill-MetricCombo $chartABox.Combo $script:Profile 'speed'\n    Fill-MetricCombo $chartBBox.Combo $script:Profile 'agl'\n    Fill-MetricCombo $historyMetric $script:Profile 'speed'",
                    selectProfileCharts,
                    "profile chart selectors");

                const string initialCharts = @"foreach ($chartBox in $script:ChartBoxes) {
        Update-Chart $chartBox.Chart @() (Selected-MetricKey $chartBox.Combo ([string]$chartBox.Preferred)) $script:Profile
    }";
                scriptText = ReplaceRequired(
                    scriptText,
                    "Update-Chart $chartABox.Chart @() (Selected-MetricKey $chartABox.Combo 'speed') $script:Profile\n    Update-Chart $chartBBox.Chart @() (Selected-MetricKey $chartBBox.Combo 'agl') $script:Profile",
                    initialCharts,
                    "initial six chart refresh");

                const string chartHandlers = @"foreach ($chartBox in $script:ChartBoxes) {
    $localChartBox = $chartBox
    $localChartBox.Combo.add_SelectedIndexChanged({
        if ($null -ne $script:Profile) {
            Update-Chart $localChartBox.Chart $script:LiveSamples \
                (Selected-MetricKey $localChartBox.Combo ([string]$localChartBox.Preferred)) $script:Profile
        }
    }.GetNewClosure())
}";
                scriptText = ReplaceRegexRequired(
                    scriptText,
                    @"\$chartABox\.Combo\.add_SelectedIndexChanged\(\{.*?\n\}\)\s*\n\$chartBBox\.Combo\.add_SelectedIndexChanged\(\{.*?\n\}\)",
                    chartHandlers,
                    "six chart selector handlers");

                const string liveChartRefresh = @"foreach ($chartBox in $script:ChartBoxes) {
                Update-Chart $chartBox.Chart $script:LiveSamples \
                    (Selected-MetricKey $chartBox.Combo ([string]$chartBox.Preferred)) $script:Profile
            }";
                scriptText = ReplaceRequired(
                    scriptText,
                    "Update-Chart $chartABox.Chart $script:LiveSamples `\n                (Selected-MetricKey $chartABox.Combo 'speed') $script:Profile\n            Update-Chart $chartBBox.Chart $script:LiveSamples `\n                (Selected-MetricKey $chartBBox.Combo 'agl') $script:Profile",
                    liveChartRefresh,
                    "live six chart refresh");

                // Rebuild profile selection without recursively re-entering Select-Profile.
                const string reloadProfiles = @"function Reload-Profiles([string]$Id) {
    $script:ReloadingProfiles=$true
    try {
        $profiles.BeginUpdate()
        $profiles.Items.Clear()
        foreach ($profile in @($script:Config.profiles)) { [void]$profiles.Items.Add($profile) }
        $profiles.DisplayMember = 'name'
        [int]$index = 0
        for ([int]$i=0; $i -lt $profiles.Items.Count; $i++) {
            if ([string]$profiles.Items[$i].id -eq $Id) { $index=$i;break }
        }
        if ($profiles.Items.Count -gt 0) { $profiles.SelectedIndex=[int]$index }
    } finally {
        $profiles.EndUpdate()
        $script:ReloadingProfiles=$false
    }
    Select-Profile
}

function Select-Profile";
                scriptText = ReplaceRegexRequired(
                    scriptText,
                    @"function Reload-Profiles\(\[string\]\$Id\) \{.*?\n\}\s*\n\s*function Select-Profile",
                    reloadProfiles,
                    "safe profile reload");
                scriptText = Regex.Replace(
                    scriptText,
                    @"\$profiles\.add_SelectedIndexChanged\(\{\s*Select-Profile\s*\}\)",
                    "$profiles.add_SelectedIndexChanged({if(-not $script:ReloadingProfiles){Select-Profile}})");
                scriptText = Regex.Replace(
                    scriptText,
                    @"Reload-Profiles ''\s*\nSelect-Profile",
                    "Reload-Profiles ''");

                if (smokeTest)
                {
                    const string showDialog = "[void]$form.ShowDialog()";
                    if (!scriptText.Contains(showDialog))
                    {
                        throw new InvalidOperationException(
                            "Startup smoke test could not find the final ShowDialog call.");
                    }
                    const string smokeBody = @"[void]$form.CreateControl()
$rootLayout.PerformLayout()
$dashboardLayout.PerformLayout()
if ($tabs.Parent -ne $rootLayout) { throw 'Tabs are not contained by the root layout.' }
if ($script:ChartBoxes.Count -ne 6) { throw 'Dashboard did not construct six charts.' }
if ($dashboardLayout.RowCount -ne 3) { throw 'Dashboard row layout is invalid.' }
$form.Dispose()
exit 0";
                    scriptText = scriptText.Replace(showDialog, smokeBody);
                }

                // A BOM keeps Japanese text reliable under Windows PowerShell 5.1.
                File.WriteAllText(runtimeScript, scriptText, new UTF8Encoding(true));

                string escapedRuntime = runtimeScript.Replace("'", "''");
                string escapedLog = errorLog.Replace("'", "''");
                string bootstrap;
                if (smokeTest)
                {
                    bootstrap =
                        "$ErrorActionPreference='Stop'\r\n" +
                        "try { & '" + escapedRuntime + "' }\r\n" +
                        "catch {\r\n" +
                        "  $detail = ($_ | Out-String)\r\n" +
                        "  Set-Content -LiteralPath '" + escapedLog + "' -Value $detail -Encoding UTF8\r\n" +
                        "  exit 1\r\n" +
                        "}\r\n";
                }
                else
                {
                    bootstrap =
                        "$ErrorActionPreference='Stop'\r\n" +
                        "try { & '" + escapedRuntime + "' }\r\n" +
                        "catch {\r\n" +
                        "  $detail = ($_ | Out-String)\r\n" +
                        "  Set-Content -LiteralPath '" + escapedLog + "' -Value $detail -Encoding UTF8\r\n" +
                        "  Add-Type -AssemblyName System.Windows.Forms\r\n" +
                        "  [System.Windows.Forms.MessageBox]::Show(" +
                        "'起動中にエラーが発生しました。`r`n`r`n' + $detail + " +
                        "'`r`nログ: " + escapedLog + "', " +
                        "'ジョリー Runner Hub', 'OK', 'Error') | Out-Null\r\n" +
                        "  exit 1\r\n" +
                        "}\r\n";
                }
                File.WriteAllText(bootstrapScript, bootstrap, new UTF8Encoding(true));

                if (File.Exists(errorLog))
                {
                    try { File.Delete(errorLog); } catch { }
                }

                ProcessStartInfo info = new ProcessStartInfo();
                info.FileName = "powershell.exe";
                info.Arguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + bootstrapScript + "\"";
                info.WorkingDirectory = appRoot;

                if (smokeTest)
                {
                    info.UseShellExecute = false;
                    info.CreateNoWindow = true;
                    using (Process process = Process.Start(info))
                    {
                        if (process == null)
                        {
                            throw new InvalidOperationException("PowerShell smoke test process did not start.");
                        }
                        if (!process.WaitForExit(60000))
                        {
                            try { process.Kill(); } catch { }
                            throw new TimeoutException("Runner Hub startup smoke test timed out after 60 seconds.");
                        }
                        if (process.ExitCode != 0)
                        {
                            string detail = File.Exists(errorLog)
                                ? File.ReadAllText(errorLog)
                                : "No startup-error.log was produced.";
                            throw new InvalidOperationException(
                                "Runner Hub startup smoke test failed.\n" + detail);
                        }
                    }
                    return;
                }

                info.UseShellExecute = true;
                Process.Start(info);
            }
            catch (Exception ex)
            {
                if (smokeTest)
                {
                    try
                    {
                        Directory.CreateDirectory(appRoot);
                        File.WriteAllText(errorLog, ex.ToString(), new UTF8Encoding(true));
                    }
                    catch { }
                    Environment.ExitCode = 1;
                    return;
                }

                MessageBox.Show(
                    "起動に失敗しました。\n\n" + ex,
                    "ジョリー Runner Hub",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
        }
    }
}
