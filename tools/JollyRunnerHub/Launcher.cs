using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;

namespace JollyRunnerHubLauncher
{
    internal static class Program
    {
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
                string scriptText = File.ReadAllText(sourceScript);

                // Windows PowerShell functions emit every uncaptured expression. Controls.Add and
                // List.Add return integers, which previously turned button/snapshot variables into
                // Object[] arrays and crashed during initial event-handler registration.
                scriptText = scriptText
                    .Replace("$top.Controls.Add($b);return $b", "[void]$top.Controls.Add($b);return $b")
                    .Replace("$lines.Add($line)", "[void]$lines.Add($line)")
                    .Replace("$rows.Add(($line | ConvertFrom-Json))", "[void]$rows.Add(($line | ConvertFrom-Json))")
                    .Replace("$aircraft.Add([pscustomobject]", "[void]$aircraft.Add([pscustomobject]")
                    .Replace("$planes.Add([pscustomobject]", "[void]$planes.Add([pscustomobject]")
                    .Replace("$events.Add([pscustomobject]", "[void]$events.Add([pscustomobject]")
                    .Replace("$cells.Add([string]$a.Name)", "[void]$cells.Add([string]$a.Name)")
                    .Replace("{$cells.Add($a.Values[[string]$m.key])}", "{[void]$cells.Add($a.Values[[string]$m.key])}");

                // Windows PowerShell 5.1 can throw "Argument types do not match" when the array
                // subexpression operator wraps a generic List<object>. Enumerate those lists directly.
                scriptText = scriptText
                    .Replace("foreach ($a in @($Snapshot.Aircraft))", "foreach ($a in $Snapshot.Aircraft)")
                    .Replace("foreach ($e in @($Snapshot.Events))", "foreach ($e in $Snapshot.Events)");

                // New-Object treats unparenthesized arithmetic in constructor arguments as a single
                // string argument. Parenthesize the status-label width calculations before execution.
                scriptText = scriptText
                    .Replace(
                        "New-Object Drawing.Size($Width-20,14)",
                        "New-Object Drawing.Size(($Width - 20),14)")
                    .Replace(
                        "New-Object Drawing.Size($Width-20,20)",
                        "New-Object Drawing.Size(($Width - 20),20)");

                // Setting SelectedIndex raises SelectedIndexChanged synchronously. The original
                // script therefore entered Select-Profile while the ComboBox was only half rebuilt;
                // PowerShell reported the nested handler failure as an exception setting
                // SelectedIndex. Suppress that event during rebuild and select exactly once after it.
                const string oldReload =
                    "function Reload-Profiles([string]$Id) {\r\n" +
                    "    $profiles.Items.Clear()\r\n" +
                    "    foreach($p in @($script:Config.profiles)){[void]$profiles.Items.Add($p)}\r\n" +
                    "    $profiles.DisplayMember='name';$index=0\r\n" +
                    "    for($i=0;$i -lt $profiles.Items.Count;$i++){if([string]$profiles.Items[$i].id -eq $Id){$index=$i;break}}\r\n" +
                    "    if($profiles.Items.Count -gt 0){$profiles.SelectedIndex=$index}\r\n" +
                    "}";
                const string newReload =
                    "function Reload-Profiles([string]$Id) {\r\n" +
                    "    $script:ReloadingProfiles=$true\r\n" +
                    "    try {\r\n" +
                    "        $profiles.BeginUpdate()\r\n" +
                    "        $profiles.Items.Clear()\r\n" +
                    "        foreach($p in @($script:Config.profiles)){[void]$profiles.Items.Add($p)}\r\n" +
                    "        $profiles.DisplayMember='name'\r\n" +
                    "        [int]$index=0\r\n" +
                    "        for([int]$i=0;$i -lt $profiles.Items.Count;$i++){if([string]$profiles.Items[$i].id -eq $Id){$index=$i;break}}\r\n" +
                    "        if($profiles.Items.Count -gt 0){$profiles.SelectedIndex=[int]$index}\r\n" +
                    "    } finally {\r\n" +
                    "        $profiles.EndUpdate()\r\n" +
                    "        $script:ReloadingProfiles=$false\r\n" +
                    "    }\r\n" +
                    "    Select-Profile\r\n" +
                    "}";
                scriptText = scriptText
                    .Replace(oldReload, newReload)
                    .Replace("$profiles.add_SelectedIndexChanged({Select-Profile})",
                        "$profiles.add_SelectedIndexChanged({if(-not $script:ReloadingProfiles){Select-Profile}})")
                    .Replace("Reload-Profiles ''\r\nSelect-Profile", "Reload-Profiles ''");

                if (smokeTest)
                {
                    const string showDialog = "[void]$form.ShowDialog()";
                    if (!scriptText.Contains(showDialog))
                    {
                        throw new InvalidOperationException(
                            "Startup smoke test could not find the final ShowDialog call.");
                    }
                    scriptText = scriptText.Replace(
                        showDialog,
                        "$form.Dispose()\r\nexit 0");
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
