using System;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows.Forms;

[StructLayout(LayoutKind.Sequential)]
public struct RECT { public int Left, Top, Right, Bottom; }

[ComImport, Guid("4E8A3389-C9D8-4BD2-B6B5-124FEE6CC14D"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IEnvironmentCompleted { [PreserveSig] int Invoke(int hr, IntPtr environment); }

[ComImport, Guid("6C4819F3-C9B7-4260-8127-C9F5BDE7F68C"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IControllerCompleted { [PreserveSig] int Invoke(int hr, IntPtr controller); }

[ComImport, Guid("B96D755E-0319-4E92-A296-23436F46A1FC"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface ICoreWebView2Environment { [PreserveSig] int CreateCoreWebView2Controller(IntPtr parent, IControllerCompleted handler); }

[ComImport, Guid("4D00C0D1-9434-4EB6-8078-8697A560334F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface ICoreWebView2Controller
{
    [PreserveSig] int get_IsVisible(out int visible);
    [PreserveSig] int put_IsVisible(int visible);
    [PreserveSig] int get_Bounds(out RECT bounds);
    [PreserveSig] int put_Bounds(RECT bounds);
    [PreserveSig] int get_ZoomFactor(out double zoom);
    [PreserveSig] int put_ZoomFactor(double zoom);
    [PreserveSig] int add_ZoomFactorChanged(IntPtr handler, out long token);
    [PreserveSig] int remove_ZoomFactorChanged(long token);
    [PreserveSig] int SetBoundsAndZoomFactor(RECT bounds, double zoom);
    [PreserveSig] int MoveFocus(int reason);
    [PreserveSig] int add_MoveFocusRequested(IntPtr handler, out long token);
    [PreserveSig] int remove_MoveFocusRequested(long token);
    [PreserveSig] int add_GotFocus(IntPtr handler, out long token);
    [PreserveSig] int remove_GotFocus(long token);
    [PreserveSig] int add_LostFocus(IntPtr handler, out long token);
    [PreserveSig] int remove_LostFocus(long token);
    [PreserveSig] int add_AcceleratorKeyPressed(IntPtr handler, out long token);
    [PreserveSig] int remove_AcceleratorKeyPressed(long token);
    [PreserveSig] int get_ParentWindow(out IntPtr parent);
    [PreserveSig] int put_ParentWindow(IntPtr parent);
    [PreserveSig] int NotifyParentWindowPositionChanged();
    [PreserveSig] int Close();
    [PreserveSig] int get_CoreWebView2(out IntPtr webview);
}

[ComImport, Guid("76ECEACB-0462-4D94-AC83-423A6793775E"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface ICoreWebView2
{
    [PreserveSig] int get_Settings(out IntPtr settings);
    [PreserveSig] int get_Source(out IntPtr uri);
    [PreserveSig] int Navigate([MarshalAs(UnmanagedType.LPWStr)] string uri);
    [PreserveSig] int NavigateToString([MarshalAs(UnmanagedType.LPWStr)] string html);
}

public class WebForm : Form, IEnvironmentCompleted, IControllerCompleted
{
    const string Page = "<title>WinCU Web Page</title><body style='background: white; color: black'>"
        + "<h1>Probe heading</h1><button>Probe button</button><input aria-label='Probe field'>"
        + "<p style='font: 64px monospace'>tick <span id='t'>0</span></p></body>"
        + "<script>var n = 0; setInterval(function () { document.getElementById('t').textContent = ++n; }, 100);</script>";

    [UnmanagedFunctionPointer(CallingConvention.StdCall, CharSet = CharSet.Unicode)]
    delegate int CreateEnvironment(string browserFolder, string userDataFolder, IntPtr options, IEnvironmentCompleted handler);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    static extern IntPtr LoadLibrary(string path);
    [DllImport("kernel32.dll", CharSet = CharSet.Ansi)]
    static extern IntPtr GetProcAddress(IntPtr module, string name);
    [DllImport("user32.dll")]
    static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int cx, int cy, uint flags);

    ICoreWebView2Controller controller;
    readonly bool background;
    protected override bool ShowWithoutActivation { get { return background; } }

    public WebForm(string loader, string dataFolder, Point? behindAt)
    {
        Text = "WinCU Web Form";
        StartPosition = FormStartPosition.Manual;
        Location = behindAt ?? new Point(140, 110);
        background = behindAt.HasValue;
        ClientSize = new Size(800, 560);
        if (background)
        {
            ShowInTaskbar = false;
            Shown += delegate { SetWindowPos(Handle, new IntPtr(1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010); };
        }
        Shown += delegate
        {
            var create = (CreateEnvironment)Marshal.GetDelegateForFunctionPointer(
                GetProcAddress(LoadLibrary(loader), "CreateCoreWebView2EnvironmentWithOptions"), typeof(CreateEnvironment));
            int hr = create(null, dataFolder, IntPtr.Zero, this);
            if (hr != 0) Text = "WinCU Web Form failed " + hr.ToString("X");
        };
        Resize += delegate { if (controller != null) controller.put_Bounds(PageBounds()); };
    }

    RECT PageBounds() { return new RECT { Left = 0, Top = 0, Right = ClientSize.Width, Bottom = ClientSize.Height }; }

    int IEnvironmentCompleted.Invoke(int hr, IntPtr environment)
    {
        if (hr != 0) { Text = "WinCU Web Form failed " + hr.ToString("X"); return 0; }
        ((ICoreWebView2Environment)Marshal.GetObjectForIUnknown(environment)).CreateCoreWebView2Controller(Handle, this);
        return 0;
    }

    int IControllerCompleted.Invoke(int hr, IntPtr pointer)
    {
        if (hr != 0) { Text = "WinCU Web Form failed " + hr.ToString("X"); return 0; }
        controller = (ICoreWebView2Controller)Marshal.GetObjectForIUnknown(pointer);
        controller.put_Bounds(PageBounds());
        controller.put_IsVisible(1);
        IntPtr view;
        controller.get_CoreWebView2(out view);
        ((ICoreWebView2)Marshal.GetObjectForIUnknown(view)).NavigateToString(Page);
        Text = "WinCU Web Form ready";
        return 0;
    }

    [STAThread]
    static void Main(string[] args)
    {
        Point? behindAt = null;
        if (args.Length == 5 && args[2] == "background") behindAt = new Point(int.Parse(args[3]), int.Parse(args[4]));
        Application.Run(new WebForm(args[0], args[1], behindAt));
    }
}
