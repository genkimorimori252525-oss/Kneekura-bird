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
        private static void Main()
        {
            try
            {
                string appRoot = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "JollyRunnerHub");
                string sourceScript = Path.Combine(appRoot, "JollyRunnerHub.ps1");
                string runtimeScript = Path.Combine(appRoot, "JollyRunnerHub.runtime.ps1");
                string bootstrapScript = Path.Combine(appRoot, "JollyRunnerHub.bootstrap.ps1");
                string errorLog = Path.Combine(appRoot, "startup-error.log");

                if (!File.Exists(sourceScript))
                {
                    MessageBox.Show(
                        "アプリ本体が見つかりません。\n" + sourceScript +
                        "\n\nGitHub Actions の Deploy Jolly Runner Hub を再実行してください。",
                        "ジョリー Runner Hub",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error);
                    return;
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

                // A BOM keeps Japanese text reliable under Windows PowerShell 5.1.
                File.WriteAllText(runtimeScript, scriptText, new UTF8Encoding(true));

                string escapedRuntime = runtimeScript.Replace("'", "''");
                string escapedLog = errorLog.Replace("'", "''");
                string bootstrap =
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
                File.WriteAllText(bootstrapScript, bootstrap, new UTF8Encoding(true));

                if (File.Exists(errorLog))
                {
                    try { File.Delete(errorLog); } catch { }
                }

                ProcessStartInfo info = new ProcessStartInfo();
                info.FileName = "powershell.exe";
                info.Arguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + bootstrapScript + "\"";
                info.WorkingDirectory = appRoot;
                info.UseShellExecute = true;
                Process.Start(info);
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "起動に失敗しました。\n\n" + ex,
                    "ジョリー Runner Hub",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
        }
    }
}
