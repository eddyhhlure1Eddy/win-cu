using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

public class TestForm : Form
{
    public static readonly Point[] Targets = {
        new Point(40, 40), new Point(600, 30), new Point(320, 90), new Point(120, 180),
        new Point(520, 200), new Point(30, 300), new Point(610, 390), new Point(260, 260),
        new Point(420, 340), new Point(180, 380), new Point(350, 20), new Point(480, 110)
    };
    const int Half = 7;

    readonly string logPath;
    readonly ToolStripStatusLabel status = new ToolStripStatusLabel("ready");
    readonly Panel canvas = new Panel();
    int dragMoves;

    readonly bool background;
    protected override bool ShowWithoutActivation { get { return background; } }

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int cx, int cy, uint flags);

    void Log(string line)
    {
        File.AppendAllText(logPath, DateTime.Now.ToString("HH:mm:ss.fff") + " " + line + "\n", new System.Text.UTF8Encoding(false));
        status.Text = line;
    }

    public TestForm(string path, Point? behindAt)
    {
        logPath = path;
        File.WriteAllText(logPath, "");
        Text = "WinCU Test Form";
        StartPosition = FormStartPosition.Manual;
        Location = behindAt ?? new Point(120, 90);
        background = behindAt.HasValue;
        if (background)
        {
            ShowInTaskbar = false;
            Shown += delegate { SetWindowPos(Handle, new IntPtr(1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010); };
        }
        ClientSize = new Size(900, 660);
        KeyPreview = true;
        KeyDown += delegate(object s, KeyEventArgs e) { Log("key " + e.KeyData); };

        MenuStrip menu = new MenuStrip();
        ToolStripMenuItem file = new ToolStripMenuItem("File");
        foreach (string name in new string[] { "New", "Open", "Save As" })
        {
            string item = name;
            file.DropDownItems.Add(item, null, delegate { Log("menu " + item); });
        }
        menu.Items.Add(file);
        MainMenuStrip = menu;

        Button alpha = new Button { Text = "Alpha", Bounds = new Rectangle(20, 40, 100, 30) };
        alpha.Click += delegate { Log("button Alpha"); };
        Button beta = new Button { Text = "Beta", Bounds = new Rectangle(130, 40, 100, 30) };
        beta.Click += delegate { Log("button Beta"); };
        CheckBox check = new CheckBox { Text = "Enable feature", Bounds = new Rectangle(250, 44, 130, 24) };
        check.CheckedChanged += delegate { Log("check " + check.Checked); };
        ComboBox combo = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Bounds = new Rectangle(400, 43, 140, 24) };
        combo.Items.AddRange(new object[] { "Red", "Green", "Blue" });
        combo.SelectedIndex = 0;
        combo.SelectedIndexChanged += delegate { Log("combo " + combo.SelectedItem); };
        Button dialog = new Button { Text = "Dialog", Bounds = new Rectangle(560, 40, 100, 30) };
        dialog.Click += delegate
        {
            Log("dialog open");
            Log("dialog " + MessageBox.Show(this, "Proceed with the test?", "WinCU Question", MessageBoxButtons.OKCancel));
        };

        Label nameLabel = new Label { Text = "Name:", Bounds = new Rectangle(20, 88, 50, 20) };
        TextBox nameBox = new TextBox { Bounds = new Rectangle(75, 85, 300, 24), AccessibleName = "Name" };
        nameBox.TextChanged += delegate { Log("name " + nameBox.Text); };
        TextBox notes = new TextBox { Multiline = true, Bounds = new Rectangle(400, 85, 480, 60), AccessibleName = "Notes" };
        notes.TextChanged += delegate { Log("notes " + notes.Text.Replace("\r\n", "\\n")); };

        ListBox list = new ListBox { Bounds = new Rectangle(20, 130, 200, 200) };
        for (int i = 1; i <= 60; i++) list.Items.Add("Item " + i);
        list.SelectedIndexChanged += delegate { Log("list " + list.SelectedItem); };
        TrackBar slider = new TrackBar { Bounds = new Rectangle(20, 350, 200, 45), Minimum = 0, Maximum = 100, AccessibleName = "Level" };
        slider.ValueChanged += delegate { Log("slider " + slider.Value); };
        TreeView tree = new TreeView { Bounds = new Rectangle(20, 400, 200, 200) };
        TreeNode fruits = tree.Nodes.Add("Fruits");
        fruits.Nodes.Add("Apple");
        fruits.Nodes.Add("Banana");
        tree.Nodes.Add("Vegetables").Nodes.Add("Carrot");
        tree.AfterSelect += delegate(object s, TreeViewEventArgs e) { Log("tree " + e.Node.Text); };
        tree.AfterExpand += delegate(object s, TreeViewEventArgs e) { Log("expanded " + e.Node.Text); };

        canvas.Bounds = new Rectangle(240, 160, 640, 440);
        canvas.BackColor = Color.White;
        canvas.BorderStyle = BorderStyle.FixedSingle;
        canvas.Paint += PaintCanvas;
        canvas.MouseDown += delegate(object s, MouseEventArgs e)
        {
            dragMoves = 0;
            Log("down " + e.Button + " " + e.X + "," + e.Y + " clicks=" + e.Clicks + " " + Hit(e.Location));
        };
        canvas.MouseMove += delegate(object s, MouseEventArgs e) { if (e.Button != MouseButtons.None) dragMoves++; };
        canvas.MouseUp += delegate(object s, MouseEventArgs e) { Log("up " + e.Button + " " + e.X + "," + e.Y + " moves=" + dragMoves); };
        canvas.MouseWheel += delegate(object s, MouseEventArgs e) { Log("wheel " + e.Delta + " at " + e.X + "," + e.Y); };

        StatusStrip bar = new StatusStrip();
        bar.Items.Add(status);
        Controls.AddRange(new Control[] { alpha, beta, check, combo, dialog, nameLabel, nameBox, notes, list, slider, tree, canvas, bar, menu });
    }

    static string Hit(Point p)
    {
        int best = -1;
        double bestDistance = double.MaxValue;
        for (int i = 0; i < Targets.Length; i++)
        {
            double d = Math.Sqrt(Math.Pow(p.X - Targets[i].X, 2) + Math.Pow(p.Y - Targets[i].Y, 2));
            if (d < bestDistance) { bestDistance = d; best = i + 1; }
        }
        bool inside = Math.Abs(p.X - Targets[best - 1].X) <= Half && Math.Abs(p.Y - Targets[best - 1].Y) <= Half;
        return (inside ? "hit" : "miss") + " target=" + best + " off=" + bestDistance.ToString("0.0");
    }

    void PaintCanvas(object sender, PaintEventArgs e)
    {
        using (Font font = new Font("Segoe UI", 9f))
        {
            for (int i = 0; i < Targets.Length; i++)
            {
                Point t = Targets[i];
                e.Graphics.FillRectangle(Brushes.Crimson, t.X - Half, t.Y - Half, 2 * Half + 1, 2 * Half + 1);
                e.Graphics.DrawString((i + 1).ToString(), font, Brushes.Black, t.X + Half + 3, t.Y - 8);
            }
        }
    }

    [STAThread]
    static void Main(string[] args)
    {
        Application.EnableVisualStyles();
        Point? behindAt = null;
        if (args.Length == 3 && args[0] == "background") behindAt = new Point(int.Parse(args[1]), int.Parse(args[2]));
        Application.Run(new TestForm(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "testform.log"), behindAt));
    }
}
