using System;
using System.Diagnostics;
using System.IO;
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
                string script = Path.Combine(appRoot, "JollyRunnerHub.ps1");
                if (!File.Exists(script))
                {
                    MessageBox.Show(
                        "アプリ本体が見つかりません。\n" + script +
                        "\n\nGitHub Actions の Deploy Jolly Runner Hub を再実行してください。",
                        "ジョリー Runner Hub",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error);
                    return;
                }

                ProcessStartInfo info = new ProcessStartInfo();
                info.FileName = "powershell.exe";
                info.Arguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File \"" + script + "\"";
                info.WorkingDirectory = appRoot;
                info.UseShellExecute = true;
                Process.Start(info);
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "起動に失敗しました。\n\n" + ex.Message,
                    "ジョリー Runner Hub",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
        }
    }
}
