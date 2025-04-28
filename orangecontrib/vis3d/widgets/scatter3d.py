from Orange.widgets.widget import OWWidget, Input, Output, Msg
from Orange.widgets.settings import Setting
from Orange.widgets import gui
from Orange.data import Table, DiscreteVariable, ContinuousVariable
from AnyQt.QtWidgets import QLabel, QComboBox, QPushButton, QFileDialog, QSpacerItem, QSizePolicy
from AnyQt.QtWebEngineWidgets import QWebEngineView
import plotly.graph_objects as go
import plotly.io as pio
from functools import partial
import plotly.express as px
from AnyQt.QtWebChannel import QWebChannel
from PyQt5.QtCore import pyqtSlot
import json

from AnyQt.QtCore import QObject, pyqtSignal, pyqtSlot
from AnyQt.QtWebChannel import QWebChannel


class CameraBridge(QObject):
    # 1) Declare a signal that notifies when the camera JSON changes
    cameraChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    @pyqtSlot(str)
    def setCamera(self, camera_json):
        # 2) Emit the JSON string
        self.cameraChanged.emit(camera_json)


class Scatter3dWidget(OWWidget):
    # Widget needs a name, or it is considered an abstract widget
    # and not shown in the menu.
    name = "Scatter3d"
    description = "3D scatter plot."
    icon = "icons/scatter3d.svg"
    priority = 10  # where in the widget order it will appear
    keywords = ["widget", "data"]
    want_main_area = True
    resizing_enabled = True
    
    selected_x = Setting("")
    selected_y = Setting("")
    selected_z = Setting("")
    selected_color = Setting("")
    selected_aspectmode = Setting("cube")
    selected_size = Setting("")
    
    class Inputs:
        # specify the name of the input and the type
        data = Input("Data", Table)

    class Outputs:
        # if there are two or more outputs, default=True marks the default output
        data = Output("Data", Table, default=True)
    
    # same class can be initiated for Error and Information messages
    class Warning(OWWidget.Warning):
        warning = Msg("My warning!")

    def __init__(self):
        super().__init__()
        self.data = None
                
        self.create_ui()
        
        
    @Inputs.data
    def set_data(self, data):
        if data:
            self.data = data
        else:
            self.data = None
        
        self._update_combos()
        self.update_plot()


            
    def commit(self):
        self.Outputs.data.send(self.data)
    
    def send_report(self):
        # self.report_plot() includes visualizations in the report
        self.report_caption(self.label)

    def _save_camera(self):
        if hasattr(self, "_last_camera"):
            self._saved_camera = self._last_camera.copy()
            # mark that we want to *use* this saved camera exactly once
            self._use_saved_camera_once = True
            self.info("📌 Camera position saved. It will be applied on the next redraw.")
            # force a redraw so you immediately see it baked in
            self.update_plot()
        else:
            self.error("No camera position to save yet.")
            

    def _on_sel(self, setting_name, combo, index):
        """Store the new combo value into our Setting, then redraw."""
        value = combo.currentText()
        setattr(self, setting_name, value)

        self.update_plot()

    def _attach_camera_listener(self, ok):
        if not ok:
            return

        js = """
        (function() {
            // 1) Insert the QWebChannel client library into the page
            var script = document.createElement('script');
            script.src = 'qrc:///qtwebchannel/qwebchannel.js';
            document.head.appendChild(script);

            script.onload = function() {
                // 2) Once it's loaded, construct the channel
                new QWebChannel(qt.webChannelTransport, function(channel) {
                    window.pybridge = channel.objects.pybridge;

                    // 3) Find the Plotly graph div
                    var gd = document.querySelector('div.js-plotly-plot');
                    if (!gd) {
                        console.warn('Plotly graph not found for camera listener');
                        return;
                    }

                    // 4) Hook into relayout events to capture camera changes
                    gd.on('plotly_relayout', function(eventdata) {
                        var cam = eventdata['scene.camera'];
                        if (cam) {
                            pybridge.setCamera(JSON.stringify(cam));
                        }
                    });
                });
            };
        })();
        """
        self.web.page().runJavaScript(js)


    def _onCamera(self, camera_json):
        try:
            self._last_camera = json.loads(camera_json)
        except ValueError:
            pass

    def _update_combos(self):
        """
        Populate each combo box with valid items, then restore the user's
        previous selection (stored in Settings) if still available.
        """
        if not self.data:
            return

        

        # List of (combo_widget, list_of_items, previously_selected_value)
        combos = [
            # X, Y, Z axes come from the numeric attributes
            (
                self.x_combo,
                [var.name for var in self.data.domain.attributes],
                self.selected_x
            ),
            (
                self.y_combo,
                [var.name for var in self.data.domain.attributes],
                self.selected_y
            ),
            (
                self.z_combo,
                [var.name for var in self.data.domain.attributes],
                self.selected_z
            ),
            # Color-by only allows discrete (categorical) variables
            (
                self.color_combo,
                [""] + [var.name for var in self.data.domain.attributes ],
                self.selected_color
            ),
            (
                  self.size_combo,
                  [""] + [var.name for var in self.data.domain.attributes
                      if isinstance(var, ContinuousVariable)],
                 self.selected_size
            ),
            # Aspectmode choices
            (
                self.aspectmode_combo,
                ["cube", "data", "auto", "manual"],
                self.selected_aspectmode
            ),
        ]

        for combo, items, old in combos:
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(items)

            # restore old selection if still valid, else default to first item
            try:
                idx = items.index(old)
            except ValueError:
                idx = 0
            combo.setCurrentIndex(idx)
            combo.blockSignals(False)


    def update_plot(self):
        if not self.data:
            return
        try:
            # Read selections
            x_name       = self.x_combo.currentText()
            y_name       = self.y_combo.currentText()
            z_name       = self.z_combo.currentText()
            color_name   = self.color_combo.currentText()
            aspectmode   = self.aspectmode_combo.currentText()
            size_name    = self.size_combo.currentText()
    
            if not x_name or not y_name or not z_name:
                return
    
            # Fetch the three axes
            x = self.data.get_column(x_name)
            y = self.data.get_column(y_name)
            z = self.data.get_column(z_name)

            hovertext   = None
    
            marker_args = {"size": 4}
            if size_name:
                sizes = self.data.get_column(size_name)
                scaled = 5 + (sizes - sizes.min()) / (sizes.ptp() or 1) * 15
                marker_args["size"] = scaled

    
            # Handle color‐by
            if color_name:
                var = self.data.domain[color_name]
                col = self.data.get_column(color_name)
                if isinstance(var, DiscreteVariable):
                    # Map each category index to a QUALITATIVE palette color
                    palette   = px.colors.qualitative.Plotly
                    # Ensure col is integer codes
                    codes     = col.astype(int)
                    color_list = [palette[i % len(palette)] for i in codes]
                    marker_args["color"] = color_list
                else:
                    # Continuous: use Viridis gradient + colorbar
                    marker_args["color"]      = col
                    marker_args["colorscale"] = "Viridis"
                    marker_args["colorbar"]   = {"title": color_name}
    
    
            # 1) Draw the main cloud
            fig = go.Figure(data=[go.Scatter3d(
                x=x, y=y, z=z,
                mode="markers",
                marker=marker_args,
                hovertext=hovertext,
                hoverinfo="text" if hovertext else "x+y+z",
                name="All points"
            )])
    
            fig.update_layout(scene=dict(
                xaxis_title=x_name,
                yaxis_title=y_name,
                zaxis_title=z_name,
                aspectmode=aspectmode
            ))
    
    
            # decide which camera to inject as the *initial* camera
            cam = None
    
            # 1) if we're flagged to apply the saved view once, do that
            if getattr(self, "_use_saved_camera_once", False):
                cam = self._saved_camera
                # clear the flag so we revert to live cam next time
                self._use_saved_camera_once = False
    
            # 2) otherwise if we have a live camera, use that
            elif hasattr(self, "_last_camera"):
                cam = self._last_camera
    
            if cam:
                fig.update_layout(scene=dict(camera=cam))
    
            # Finally render
            self.web.setHtml(fig.to_html(include_plotlyjs="cdn"))
            self._last_figure = fig
    
            n_points = len(x)   # or len(self.data) if you prefer
            self.count_label.setText(f"Points: {n_points}")
    
        except Exception as e:
            self.error(f"Plot error: {e}")


    def create_ui(self):
        # Axis selection
        self.controlArea.layout().addWidget(QLabel("Select Columns:"))
        self.x_combo = QComboBox()
        self.y_combo = QComboBox()
        self.z_combo = QComboBox()
        self.color_combo = QComboBox()
        self.size_combo = QComboBox()
        self.aspectmode_combo = QComboBox()

        self.controlArea.layout().addWidget(QLabel("X Axis:"))
        self.controlArea.layout().addWidget(self.x_combo)
        self.controlArea.layout().addWidget(QLabel("Y Axis:"))
        self.controlArea.layout().addWidget(self.y_combo)
        self.controlArea.layout().addWidget(QLabel("Z Axis:"))
        self.controlArea.layout().addWidget(self.z_combo)

        self.controlArea.layout().addWidget(QLabel("Color by (categorical):"))
        self.controlArea.layout().addWidget(self.color_combo)

        # Size‐by combo (continuous only)
        self.controlArea.layout().addWidget(QLabel("Size by (numeric):"))
        self.controlArea.layout().addWidget(self.size_combo)

        self.size_combo.currentIndexChanged.connect(
            lambda idx: self._on_sel("selected_size", self.size_combo)
        )


        self.controlArea.layout().addWidget(QLabel("Aspect Mode:"))
        self.aspectmode_combo.addItems(["cube", "data", "auto", "manual"])
        self.controlArea.layout().addWidget(self.aspectmode_combo)


        # After creating self.x_combo, self.y_combo, …, self.aspectmode_combo
        for attr, combo in [
            ("selected_x",       self.x_combo),
            ("selected_y",       self.y_combo),
            ("selected_z",       self.z_combo),
            ("selected_color",   self.color_combo),
            ("selected_size",    self.size_combo),
            ("selected_aspectmode", self.aspectmode_combo),
        ]:
            # partial will bind attr and combo; the index arg comes from the signal
            combo.currentIndexChanged.connect(partial(self._on_sel, attr, combo))
        
        
        # plotly camera save/restore
        self.save_camera_btn = QPushButton("Save Camera")
        self.controlArea.layout().addWidget(self.save_camera_btn)
        self.save_camera_btn.clicked.connect(self._save_camera)

        # initialize storage for the saved camera
        self._saved_camera = None
        self._use_saved_camera_once = False


        self.count_label = QLabel("Points: 0")
        self.controlArea.layout().addWidget(self.count_label)



        # Spacer to keep controls at top
        spacer = QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.controlArea.layout().addItem(spacer)

        # Export buttons
        self.export_html_btn = QPushButton("Export as HTML")
        self.export_png_btn = QPushButton("Export as PNG")
        self.controlArea.layout().addWidget(self.export_html_btn)
        self.controlArea.layout().addWidget(self.export_png_btn)
        self.export_html_btn.clicked.connect(self.export_html)
        self.export_png_btn.clicked.connect(self.export_png)

        # Plot display
        self.web = QWebEngineView(self)

        # Create and register the bridge
        self._bridge = CameraBridge(self)
        channel = QWebChannel(self.web.page())
        self.web.page().setWebChannel(channel)
        channel.registerObject("pybridge", self._bridge)

        # Whenever the bridge’s signal fires, update the stored camera
        self._bridge.cameraChanged.connect(self._onCamera)

        # Only after wiring the bridge do we inject our JS
        self.web.page().loadFinished.connect(self._attach_camera_listener)

        self.mainArea.layout().addWidget(self.web)
        
    def export_html(self):
        if hasattr(self, "_last_figure"):
            path, _ = QFileDialog.getSaveFileName(self, "Export as HTML", "", "HTML files (*.html)")
            if path:
                self._last_figure.write_html(path)

    def export_png(self):
        if hasattr(self, "_last_figure"):
            path, _ = QFileDialog.getSaveFileName(self, "Export as PNG", "", "PNG files (*.png)")
            if path:
                try:
                    pio.write_image(self._last_figure, path)
                except Exception as e:
                    self.error(f"Failed to export PNG: {e}")


if __name__ == "__main__":
    from Orange.widgets.utils.widgetpreview import WidgetPreview  # since Orange 3.20.0
    WidgetPreview(Scatter3dWidget).run()
