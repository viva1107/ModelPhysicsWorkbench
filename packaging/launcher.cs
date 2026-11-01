// Model Physics Workbench.exe：使用随包 runtime\pythonw.exe 启动模型物理工具。
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

[assembly: System.Reflection.AssemblyTitle("Model Physics Workbench")]
[assembly: System.Reflection.AssemblyProduct("Model Physics Workbench")]
[assembly: System.Reflection.AssemblyDescription("Generate creature, spell and equipment PHY2 tables from retail M2 physics")]

static class Launcher
{
    const string Title = "Retroport 模型物理工具";

    [STAThread]
    static int Main(string[] args)
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(root, "runtime", "pythonw.exe");
        string code = Path.Combine(root, "app");
        if (!File.Exists(python))
        {
            python = OnPath("pythonw.exe");
            code = root;
        }
        if (python == null)
        {
            Fail("缺少 Python 运行环境。请完整解压 ZIP，并保留 EXE 旁边的 runtime 和 app 目录。");
            return 1;
        }
        if (!Directory.Exists(Path.Combine(code, "retroport")))
        {
            Fail("程序文件不完整：找不到 " + Path.Combine(code, "retroport"));
            return 1;
        }
        ProcessStartInfo start = new ProcessStartInfo(python, "-m retroport.workbench.app");
        start.WorkingDirectory = code;
        start.UseShellExecute = false;
        start.EnvironmentVariables["PYTHONPATH"] = code;
        try { Process.Start(start); }
        catch (Exception e)
        {
            Fail("工具无法启动：\n\n" + e.Message);
            return 1;
        }
        return 0;
    }

    static string OnPath(string exe)
    {
        foreach (string dir in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator))
        {
            try
            {
                string full = Path.Combine(dir.Trim().Trim('"'), exe);
                if (File.Exists(full)) return full;
            }
            catch (ArgumentException) { }
        }
        return null;
    }

    static void Fail(string text)
    {
        MessageBox.Show(text, Title, MessageBoxButtons.OK, MessageBoxIcon.Error);
    }
}
