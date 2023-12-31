"""
VollSeg Napari MTrack .

Made by Kapoorlabs, 2022
"""

import functools
import time
from pathlib import Path
from typing import List, Union
from skimage import morphology
import napari
import numpy as np
import pandas as pd
import seaborn as sns
from caped_ai_tabulour._tabulour import Tabulour, pandasModel
from magicgui import magicgui
from magicgui import widgets as mw
from napari.qt.threading import thread_worker
from psygnal import Signal
from qtpy.QtWidgets import QSizePolicy, QTabWidget, QVBoxLayout, QWidget
from skimage.morphology import thin
import btrack
ITERATIONS = 20
MAXTRIALS = 100


def plugin_wrapper_btrack():

    from caped_ai_btrack.Skel import Skeletonizer
    from csbdeep.utils import axes_check_and_normalize, axes_dict, load_json
    from vollseg import UNET, VollSeg
    from vollseg.pretrained import get_model_folder, get_registered_models

    from ._temporal_plots import TemporalStatistics

    DEBUG = False

    def _raise(e):
        if isinstance(e, BaseException):
            raise e
        else:
            raise ValueError(e)

    def get_data(image, debug=DEBUG):

        image = image.data

        return np.asarray(image)

    def abspath(root, relpath):
        root = Path(root)
        if root.is_dir():
            path = root / relpath
        else:
            path = root.parent / relpath
        return str(path.absolute())

    def change_handler(*widgets, init=False, debug=DEBUG):
        def decorator_change_handler(handler):
            @functools.wraps(handler)
            def wrapper(*args):
                source = Signal.sender()
                emitter = Signal.current_emitter()
                if debug:
                    print(f"{str(emitter.name).upper()}: {source.name}")
                return handler(*args)

            for widget in widgets:
                widget.changed.connect(wrapper)
                if init:
                    widget.changed(widget.value)
            return wrapper

        return decorator_change_handler

    _models_vollseg, _aliases_vollseg = get_registered_models(UNET)

    models_vollseg = [
        ((_aliases_vollseg[m][0] if len(_aliases_vollseg[m]) > 0 else m), m)
        for m in _models_vollseg
    ]

    worker = None
    model_vollseg_configs = dict()
    model_selected_vollseg = None

    PRETRAINED = UNET
    CUSTOM_VOLLSEG = "CUSTOM_VOLLSEG"
    vollseg_model_type_choices = [
        ("PreTrained", PRETRAINED),
        ("Custom U-Net", CUSTOM_VOLLSEG),
        ("NOSEG", "NOSEG"),
    ]

    track_model_type_choices = [
        ("BTrack", btrack)
    ]
    default_tracking_config = {
  "name": "Default",
  "version": "0.5.0",
  "verbose": False,
  "motion_model": {
    "measurements": 3,
    "states": 6,
    "A": [
      1.0, 0.0, 0.0, 1.0, 0.0, 0.0,
      0.0, 1.0, 0.0, 0.0, 1.0, 0.0,
      0.0, 0.0, 1.0, 0.0, 0.0, 1.0,
      0.0, 0.0, 0.0, 1.0, 0.0, 0.0,
      0.0, 0.0, 0.0, 0.0, 1.0, 0.0,
      0.0, 0.0, 0.0, 0.0, 0.0, 1.0
    ],
    "H": [
      1.0, 0.0, 0.0, 0.0, 0.0, 0.0,
      0.0, 1.0, 0.0, 0.0, 0.0, 0.0,
      0.0, 0.0, 1.0, 0.0, 0.0, 0.0
    ],
    "P": [
      15.0, 0.0, 0.0, 0.0, 0.0, 0.0,
      0.0, 15.0, 0.0, 0.0, 0.0, 0.0,
      0.0, 0.0, 15.0, 0.0, 0.0, 0.0,
      0.0, 0.0, 0.0, 150.0, 0.0, 0.0,
      0.0, 0.0, 0.0, 0.0, 150.0, 0.0,
      0.0, 0.0, 0.0, 0.0, 0.0, 150.0
    ],
    "R": [
      5.0, 0.0, 0.0,
      0.0, 5.0, 0.0,
      0.0, 0.0, 5.0
    ],
    "G": [ 7.5, 7.5, 7.5, 15.0, 15.0, 15.0],
    "Q": [
      56.25, 56.25, 56.25, 112.5, 112.5, 112.5,
      56.25, 56.25, 56.25, 112.5, 112.5, 112.5,
      56.25, 56.25, 56.25, 112.5, 112.5, 112.5,
      112.5, 112.5, 112.5, 225.0, 225.0, 225.0,
      112.5, 112.5, 112.5, 225.0, 225.0, 225.0,
      112.5, 112.5, 112.5, 225.0, 225.0, 225.0
    ],
    "dt": 1.0,
    "accuracy": 7.5,
    "max_lost": 5,
    "prob_not_assign": 0.001,
    "name": "cell_motion"
  },
  "object_model": None,
  "hypothesis_model": {
    "hypotheses": [
      "P_FP",
      "P_init",
      "P_term",
      "P_link",
      "P_branch",
      "P_dead"
    ],
    "lambda_time": 5.0,
    "lambda_dist": 3.0,
    "lambda_link": 10.0,
    "lambda_branch": 50.0,
    "eta": 1e-10,
    "theta_dist": 20.0,
    "theta_time": 5.0,
    "dist_thresh": 37.0,
    "time_thresh": 2.0,
    "apop_thresh": 5,
    "segmentation_miss_rate": 0.1,
    "apoptosis_rate": 0.001,
    "relax": True,
    "name": "cell_hypothesis"
  },
  "max_search_radius": 100.0,
  "return_kalman": False,
  "volume": None,
  "update_method": 0,
  "optimizer_options": {
    "tm_lim": 60000
  },
  "features": [],
  "tracking_updates": [
    1
  ]
}
    cell_tracking_config = {
        "TrackerConfig":
    {
      "MotionModel":
        {
          "name": "cell_motion",
          "dt": 1.0,
          "measurements": 3,
          "states": 6,
          "accuracy": 7.5,
          "prob_not_assign": 0.001,
          "max_lost": 5,
          "A": {
            "matrix": [1,0,0,1,0,0,
                       0,1,0,0,1,0,
                       0,0,1,0,0,1,
                       0,0,0,1,0,0,
                       0,0,0,0,1,0,
                       0,0,0,0,0,1]
          },
          "H": {
            "matrix": [1,0,0,0,0,0,
                       0,1,0,0,0,0,
                       0,0,1,0,0,0]
          },
          "P": {
            "sigma": 150.0,
            "matrix": [0.1,0,0,0,0,0,
                       0,0.1,0,0,0,0,
                       0,0,0.1,0,0,0,
                       0,0,0,1,0,0,
                       0,0,0,0,1,0,
                       0,0,0,0,0,1]
          },
          "G": {
            "sigma": 15.0,
            "matrix": [0.5,0.5,0.5,1,1,1]

          },
          "R": {
            "sigma": 5.0,
            "matrix": [1,0,0,
                       0,1,0,
                       0,0,1]
          }
        },
      "ObjectModel":
        {},
      "HypothesisModel":
        {
          "name": "cell_hypothesis",
          "hypotheses": ["P_FP", "P_init", "P_term", "P_link", "P_branch", "P_dead"],
          "lambda_time": 5.0,
          "lambda_dist": 3.0,
          "lambda_link": 10.0,
          "lambda_branch": 50.0,
          "eta": 1e-10,
          "theta_dist": 20.0,
          "theta_time": 5.0,
          "dist_thresh": 40,
          "time_thresh": 2,
          "apop_thresh": 5,
          "segmentation_miss_rate": 0.1,
          "apoptosis_rate": 0.001,
          "relax": True
        }
    }
    }
    DEFAULTS_MODEL = dict(
        vollseg_model_type=CUSTOM_VOLLSEG,
        tracking_model_type=btrack,
        model_vollseg=models_vollseg[0][0],
        model_vollseg_none="NOSEG",
        axes="TYX",
        microscope_calibration_space=1,
        microscope_calibration_time=1,
    )

    model_selected_tracking = DEFAULTS_MODEL["tracking_model_type"]
    DEFAULTS_SEG_PARAMETERS = dict(n_tiles=(1, 1, 1))

    DEFAULTS_PRED_PARAMETERS = dict(
       max_search_radius = 50
    )

    def get_model_tracking(tracking_model_type):

        return tracking_model_type

    @functools.lru_cache(maxsize=None)
    def get_model_vollseg(vollseg_model_type, model_vollseg):
        if vollseg_model_type == CUSTOM_VOLLSEG:
            path_vollseg = Path(model_vollseg)
            path_vollseg.is_dir() or _raise(
                FileNotFoundError(f"{path_vollseg} is not a directory")
            )

            model_class_vollseg = UNET
            return model_class_vollseg(
                None, name=path_vollseg.name, basedir=str(path_vollseg.parent)
            )

        elif vollseg_model_type != DEFAULTS_MODEL["model_vollseg_none"]:
            return vollseg_model_type.local_from_pretrained(model_vollseg)
        else:
            return None

    @magicgui(
        
         max_search_radius=dict(
            widget_type="SpinBox",
            label="Maximum number of consecutive frames object was not detected",
            min=0.0,
            step=1,
            value=DEFAULTS_PRED_PARAMETERS["max_search_radius"],
        ),
        tracking_model_type=dict(
            widget_type="RadioButtons",
            label="Tracking Model Type",
            orientation="horizontal",
            choices=track_model_type_choices,
            value=DEFAULTS_MODEL["tracking_model_type"],
        ),
        defaults_params_button=dict(
            widget_type="PushButton", text="Restore Parameter Defaults"
        ),
        call_button=False,
    )
    def plugin_tracking_parameters(
        max_search_radius,
        tracking_model_type,
        defaults_params_button,
    ) -> List[napari.types.LayerDataTuple]:

        return plugin_tracking_parameters

    kapoorlogo = abspath(__file__, "resources/kapoorlogo.png")
    citation = Path("https://doi.org/10.1038/s41598-018-37767-1")

    @magicgui(
        label_head=dict(
            widget_type="Label",
            label=f'<h1> <img src="{kapoorlogo}"> </h1>',
            value=f'<h5><a href=" {citation}"> BTrack: Tracking of tissue dynamic ends in 2D and 3D + time</a></h5>',
        ),
        image=dict(label="Input Image"),
        axes=dict(
            widget_type="LineEdit",
            label="Image Axes",
            value=DEFAULTS_MODEL["axes"],
        ),
        vollseg_model_type=dict(
            widget_type="RadioButtons",
            label="VollSeg Model Type",
            orientation="horizontal",
            choices=vollseg_model_type_choices,
            value=DEFAULTS_MODEL["vollseg_model_type"],
        ),
        model_vollseg=dict(
            widget_type="ComboBox",
            visible=False,
            label="Pre-trained UNET Model",
            choices=models_vollseg,
            value=DEFAULTS_MODEL["model_vollseg"],
        ),
        model_vollseg_none=dict(
            widget_type="Label", visible=False, label="NOSEG"
        ),
        model_folder_vollseg=dict(
            widget_type="FileEdit",
            visible=False,
            label="Custom VollSeg",
            mode="d",
        ),
        microscope_calibration_space=dict(
            widget_type="FloatSpinBox",
            label="Pixel size space (X)",
            min=0.000001,
            step=0.00005,
            value=DEFAULTS_MODEL["microscope_calibration_space"],
        ),
        microscope_calibration_time=dict(
            widget_type="FloatSpinBox",
            label="Calibration time (T)",
            min=0.000000001,
            step=0.00005,
            value=DEFAULTS_MODEL["microscope_calibration_time"],
        ),
        n_tiles=dict(
            widget_type="LiteralEvalLineEdit",
            label="Number of Tiles",
            value=DEFAULTS_SEG_PARAMETERS["n_tiles"],
        ),
        defaults_model_button=dict(
            widget_type="PushButton", text="Restore Model Defaults"
        ),
        manual_compute_button=dict(
            widget_type="PushButton", text="Retrack"
        ),
        recompute_current_button=dict(
            widget_type="PushButton", text="Recompute current skeletons"
        ),
        progress_bar=dict(label=" ", min=0, max=0, visible=False),
        layout="vertical",
        persist=False,
        call_button=True,
    )
    def plugin(
        viewer: napari.Viewer,
        label_head,
        image: napari.layers.Image,
        axes,
        vollseg_model_type,
        model_vollseg,
        model_vollseg_none,
        model_folder_vollseg,
        microscope_calibration_space,
        microscope_calibration_time,
        n_tiles,
        defaults_model_button,
        manual_compute_button,
        recompute_current_button,
        progress_bar: mw.ProgressBar,
    ) -> List[napari.types.LayerDataTuple]:

        x = get_data(image)
        print(x.shape)
        axes = axes_check_and_normalize(axes, length=x.ndim)
        nonlocal worker
        progress_bar.label = "Starting BTrack"
        if model_selected_vollseg is not None:
            vollseg_model = get_model_vollseg(*model_selected_vollseg)
        else:
            vollseg_model = None    
        if len(x.shape) == 3: 
           axes_out = list('TYX')
        if len(x.shape) == 4:
            axes_out = list('TZYX')   
        if vollseg_model is not None:
            assert vollseg_model._axes_out[-1] == "C"
            axes_out = list(vollseg_model._axes_out[:-1])
        scale_in_dict = dict(zip(axes, image.scale))
        scale_out = [scale_in_dict.get(a, 1.0) for a in axes_out]
        tracking_model = get_model_tracking(model_selected_tracking)

        if "T" in axes:
            t = axes_dict(axes)["T"]
            n_frames = x.shape[0]
            print(n_frames)
            def progress_thread(current_time):

                progress_bar.label = "Skeletonizing tissue in frame " + str(current_time)
                progress_bar.range = (0, n_frames - 1)
                progress_bar.value = current_time
                progress_bar.show()

        if "T" in axes and axes_out is not None:
            x_reorder = np.moveaxis(x, t, 0)

            axes_reorder = axes.replace("T", "")
            if 'T' not in axes_out:
               axes_out.insert(t, "T")
            # determine scale for output axes
            scale_in_dict = dict(zip(axes, image.scale))
            scale_out = [scale_in_dict.get(a, 1.0) for a in axes_out]
            worker = _Unet_time(
                vollseg_model,
                x_reorder,
                axes_reorder,
                scale_out,
                t,
                x,
                tracking_model,
            )
            worker.returned.connect(return_segment_unet_time)
            worker.yielded.connect(progress_thread)
        else:
            raise ValueError("Time dimension not found")

        progress_bar.hide()

    plugin.label_head.value = '<br>Citation <tt><a href="https://doi.org/10.1101/2022.08.30.505826" style="color:gray;">BTrack PubMed</a></tt>'
    plugin.label_head.native.setSizePolicy(
        QSizePolicy.MinimumExpanding, QSizePolicy.Fixed
    )

    def return_segment_unet_time(pred):

        layer_data, time_line_locations, scale_out = pred
        ndim = len(get_data(plugin.image.value).shape)
        name_remove = ["Fits_BTrack", "Seg_BTrack", "Seg_BTrack_Dots"]
        for layer in list(plugin.viewer.value.layers):
            if any(name in layer.name for name in name_remove):
                plugin.viewer.value.layers.remove(layer)

        plugin.viewer.value.add_labels(layer_data, name="Seg_BTrack")

        markers = np.zeros_like(layer_data)                      
        for (time,Coordinates) in time_line_locations.items():

                if ndim==3:
               
                  coordinates_int = np.round(Coordinates).astype(int)
                  markers_raw = markers[time]
                  markers_raw[tuple(coordinates_int.T)] = 1 + np.arange(len(Coordinates))
         
                if ndim==4:
                   
                    coordinates_int = np.round(Coordinates).astype(int)
                    markers_raw = markers[time]
                    markers_raw[tuple(coordinates_int.T)] = 1 + np.arange(len(Coordinates))

                    
        if ndim == 3:
            for j in range(markers.shape[0]):
                    markers[j] = morphology.dilation(
                                    markers_raw.astype("uint16"), morphology.disk(2)
                                )           
        if ndim == 4:

             for j in range(markers.shape[0]):
                markers[j] = morphology.dilation(
                        markers_raw.astype("uint16"), morphology.ball(2)
                    )


                    
                    
        plugin.viewer.value.add_labels(markers, name="Seg_BTrack_Dots")      
        if ndim == 4:   
            face_color = [0] * 4
        if ndim == 3:
            face_color = [0] * 3   
        time_line_array = []     
        for (time, Coordinates) in time_line_locations.items():  
            for cord in Coordinates:
              time_line_array.append((time, *cord))    
        plugin.viewer.value.add_points(
            np.asarray(time_line_array),
            name="Fits_BTrack",
            face_color=face_color,
            edge_color="red",
            edge_width=1,
        )
        #_perform_tracking(markers, layer_data)

    def _perform_tracking(markers, layer_data):
        objects = btrack.utils.segmentation_to_objects(
                    markers
                    )
        ndim = len(layer_data.shape)
        with btrack.BayesianTracker() as tracker:
            tracker.configure(default_tracking_config)
            tracker.append(objects)
            if ndim == 4:
              #YXZ
              tracker.volume=((0, layer_data.shape[2]), (0, layer_data.shape[3]), (0, layer_data.shape[1]))
            if ndim == 3:
                #XY
                tracker.volume=((0, layer_data.shape[1]), (0, layer_data.shape[2]))  
            tracker.optimize()
            # store the tracks
            tracks = tracker.tracks
            # store the configuration
            cfg = tracker.configuration
            data, properties, graph = tracker.to_napari(ndim -1)

        plugin.viewer.add_tracks(data, properties=properties, graph=graph)



    def plot_main():
        if plot_class.scroll_layout.count() > 0:
            plot_class._reset_container(plot_class.scroll_layout)
        _refreshPlotData(table_tab._data.get_data())


    @thread_worker(connect={"returned": [return_segment_unet_time]})
    def _Unet_time(
        model_unet, x_reorder, axes_reorder, scale_out, t, x, tracking_model
    ):
        pre_res = []
        yield 0
        correct_label_present = []
        any_label_present = []
        for layer in list(plugin.viewer.value.layers):
            if (
                isinstance(layer, napari.layers.Labels)
                and layer.data.shape == get_data(plugin.image.value).shape
            ):
                correct_label_present.append(True)
            elif (
                isinstance(layer, napari.layers.Labels)
                and layer.data.shape != get_data(plugin.image.value).shape
            ):
                correct_label_present.append(False)

            if not isinstance(layer, napari.layers.Labels):
                any_label_present.append(False)
            elif isinstance(layer, napari.layers.Labels):
                any_label_present.append(True)
        if (
            any(correct_label_present) is False
            or any(any_label_present) is False
        ):

            for count, _x in enumerate(x_reorder):
                yield count 
                pre_res.append(
                    VollSeg(
                        _x,
                        unet_model=model_unet,
                        n_tiles=plugin.n_tiles.value,
                        axes=axes_reorder,
                    )
                )

            unet_mask, skeleton = zip(*pre_res)

            unet_mask = np.asarray(unet_mask)

            unet_mask = unet_mask > 0
            unet_mask = np.moveaxis(unet_mask, 0, t)
            unet_mask = np.reshape(unet_mask, x.shape)

            skeleton = np.asarray(skeleton)
            skeleton = skeleton > 0
            skeleton = np.moveaxis(skeleton, 0, t)
            skeleton = np.reshape(skeleton, x.shape)

            layer_data = unet_mask
            
            

        else:
            for layer in list(plugin.viewer.value.layers):
                if (
                    isinstance(layer, napari.layers.Labels)
                    and layer.data.shape == get_data(plugin.image.value).shape
                ):

                    layer_data = layer.data
       
        time_line_locations = {}
        ndim = len(layer_data.shape)
        for count, i in enumerate(range(layer_data.shape[0])):
                yield count
                skeletonizer = Skeletonizer(layer_data[i].astype(np.uint16))
                for point in skeletonizer.end_points:
                       if ndim == 3:
                            y, x = point 
                            if i not in time_line_locations:
                                time_line_locations[i] = [(y,x)]
                            else:
                                y_x_list = time_line_locations[i]
                                y_x_list.append((y,x))
                                time_line_locations[i] = y_x_list
                       if ndim == 4:
                            z, y, x = point 
                            if i not in time_line_locations:
                                time_line_locations[i] = [(z,y,x)]
                            else:
                                z_y_x_list = time_line_locations[i]
                                z_y_x_list.append((z,y,x))
                                time_line_locations[i] = z_y_x_list 
        pred = layer_data, time_line_locations, scale_out
        return pred

   

    widget_for_vollseg_modeltype = {
        UNET: plugin.model_vollseg,
        "NOSEG": plugin.model_vollseg_none,
        CUSTOM_VOLLSEG: plugin.model_folder_vollseg,
    }

    tabs = QTabWidget()

    parameter_skeleton_tab = QWidget()
    _parameter_skeleton_tab_layout = QVBoxLayout()
    parameter_skeleton_tab.setLayout(_parameter_skeleton_tab_layout)
    _parameter_skeleton_tab_layout.addWidget(plugin_tracking_parameters.native)
    tabs.addTab(parameter_skeleton_tab, "Tracking Parameter Selection")

    plot_class = TemporalStatistics(tabs)
    plot_tab = plot_class.stat_plot_tab
    tabs.addTab(plot_tab, "Analysis Plots")

    table_tab = Tabulour()
    table_tab.clicked.connect(table_tab._on_user_click)
    tabs.addTab(table_tab, "Table")

    plugin.native.layout().addWidget(tabs)
    plugin.recompute_current_button.native.setStyleSheet(
        "background-color: green"
    )
    plugin.manual_compute_button.native.setStyleSheet(
        "background-color: orange"
    )

    def _refreshPlotData(df):

        plot_class._repeat_after_plot()
        ax = plot_class.stat_ax
        ax.cla()

        sns.violinplot(x="Growth_Rate", data=df, ax=ax)

        ax.set_xlabel("Growth Rate")

        plot_class._repeat_after_plot()
        ax = plot_class.stat_ax

        sns.violinplot(x="Average_Displacement", data=df, ax=ax)

        ax.set_xlabel("Average Displacement")

        plot_class._repeat_after_plot()
        ax = plot_class.stat_ax
        

    def _refreshTableData(df: pd.DataFrame):

        table_tab.data = pandasModel(df)
        table_tab.viewer = plugin.viewer.value
        table_tab.time_key = "File_Index"
        table_tab._set_model()
        if plot_class.scroll_layout.count() > 0:
            plot_class._reset_container(plot_class.scroll_layout)
        _refreshPlotData(df)

    def select_model_skeleton(key):
        nonlocal model_selected_tracking
        model_selected_tracking = key

    def widgets_inactive(*widgets, active):
        for widget in widgets:
            widget.visible = active

    def widgets_valid(*widgets, valid):
        for widget in widgets:
            widget.native.setStyleSheet(
                "" if valid else "background-color: red"
            )

    class Updater:
        def __init__(self, debug=DEBUG):
            from types import SimpleNamespace

            self.debug = debug
            self.valid = SimpleNamespace(
                **{
                    k: False
                    for k in ("image_axes", "model_vollseg", "n_tiles")
                }
            )
            self.args = SimpleNamespace()
            self.viewer = None

        def __call__(self, k, valid, args=None):
            assert k in vars(self.valid)
            setattr(self.valid, k, bool(valid))
            setattr(self.args, k, args)
            self._update()

        def help(self, msg):
            if self.viewer is not None:
                self.viewer.help = msg
            elif len(str(msg)) > 0:
                print(f"HELP: {msg}")

        def _update(self):

            # try to get a hold of the viewer (can be None when plugin starts)
            if self.viewer is None:
                # TODO: when is this not safe to do and will hang forever?
                # while plugin.viewer.value is None:
                #     time.sleep(0.01)
                if plugin.viewer.value is not None:
                    self.viewer = plugin.viewer.value
                    if DEBUG:
                        print("GOT viewer")

            def _model(valid):
                widgets_valid(
                    plugin.model_vollseg,
                    plugin.model_folder_vollseg.line_edit,
                    valid=valid,
                )
                if valid:
                    config_vollseg = self.args.model_vollseg
                    axes_vollseg = config_vollseg.get(
                        "axes",
                        "YXC"[-len(config_vollseg["unet_input_shape"]) :],
                    )

                    plugin.model_folder_vollseg.line_edit.tooltip = ""
                    return axes_vollseg, config_vollseg
                else:
                    plugin.model_folder_vollseg.line_edit.tooltip = (
                        "Invalid model directory"
                    )

            def _image_axes(valid):
                axes, image, err = getattr(
                    self.args, "image_axes", (None, None, None)
                )

                if axes == "YX":
                    plugin.recompute_current_button.hide()
                widgets_valid(
                    plugin.axes,
                    valid=(
                        valid
                        or (image is None and (axes is None or len(axes) == 0))
                    ),
                )

                if valid:
                    plugin.axes.tooltip = "\n".join(
                        [
                            f"{a} = {s}"
                            for a, s in zip(axes, get_data(image).shape)
                        ]
                    )
                    return axes, image
                else:
                    if err is not None:
                        err = str(err)
                        err = err[:-1] if err.endswith(".") else err
                        plugin.axes.tooltip = err
                        # warn(err) # alternative to tooltip (gui doesn't show up in ipython)
                    else:
                        plugin.axes.tooltip = ""

            def _n_tiles(valid):
                n_tiles, image, err = getattr(self.args, "n_tiles", (1, 1, 1))
                widgets_valid(plugin.n_tiles, valid=(valid or image is None))
                if valid:
                    plugin.n_tiles.tooltip = "\n".join(
                        [
                            f"{t}: {s}"
                            for t, s in zip(n_tiles, get_data(image).shape)
                        ]
                    )
                    return n_tiles
                else:
                    msg = str(err) if err is not None else ""
                    plugin.n_tiles.tooltip = msg

            def _no_tiling_for_axis(axes_image, n_tiles, axis):
                if n_tiles is not None and axis in axes_image:
                    return n_tiles[axes_dict(axes_image)[axis]] == 1
                return True

            def _restore():
                widgets_valid(
                    plugin.image, valid=plugin.image.value is not None
                )

            all_valid = False
            help_msg = ""

            if (
                self.valid.image_axes
                and self.valid.n_tiles
                and self.valid.model_vollseg
            ):
                axes_image, image = _image_axes(True)
                (axes_model_vollseg, config_vollseg) = _model(True)
                n_tiles = _n_tiles(True)
                if not _no_tiling_for_axis(axes_image, n_tiles, "C"):
                    # check if image axes and n_tiles are compatible
                    widgets_valid(plugin.n_tiles, valid=False)
                    err = "number of tiles must be 1 for C axis"
                    plugin.n_tiles.tooltip = err
                    _restore()
                elif not _no_tiling_for_axis(axes_image, n_tiles, "T"):
                    # check if image axes and n_tiles are compatible
                    widgets_valid(plugin.n_tiles, valid=False)
                    err = "number of tiles must be 1 for T axis"
                    plugin.n_tiles.tooltip = err
                    _restore()

                else:
                    # check if image and models are compatible
                    ch_model_vollseg = config_vollseg["n_channel_in"]

                    ch_image = (
                        get_data(image).shape[axes_dict(axes_image)["C"]]
                        if "C" in axes_image
                        else 1
                    )
                    all_valid = (
                        set(axes_model_vollseg.replace("C", ""))
                        == set(axes_image.replace("C", "").replace("T", ""))
                        and ch_model_vollseg == ch_image
                    )

                    widgets_valid(
                        plugin.image,
                        plugin.model_vollseg,
                        plugin.model_folder_vollseg.line_edit,
                        valid=all_valid,
                    )
                    if all_valid:
                        help_msg = ""
                    else:
                        help_msg = f'Model with axes {axes_model_vollseg.replace("C", f"C[{ch_model_vollseg}]")} and image with axes {axes_image.replace("C", f"C[{ch_image}]")} not compatible'
            else:

                _image_axes(self.valid.image_axes)
                _n_tiles(self.valid.n_tiles)
                _model(self.valid.model_vollseg)

                _restore()

            self.help(help_msg)
            plugin.call_button.enabled = all_valid
            # widgets_valid(plugin.call_button, valid=all_valid)
            if self.debug:
                print(
                    f"valid ({all_valid}):",
                    ", ".join(
                        [f"{k}={v}" for k, v in vars(self.valid).items()]
                    ),
                )

    update_vollseg = Updater()

    def select_model_vollseg(key):
        nonlocal model_selected_vollseg
        if key is not None:
            model_selected_vollseg = key
            config_vollseg = model_vollseg_configs.get(key)
            update_vollseg(
                "model_vollseg", config_vollseg is not None, config_vollseg
            )
        if (
            plugin.vollseg_model_type.value
            == DEFAULTS_MODEL["model_vollseg_none"]
        ):
            model_selected_vollseg = None

    @change_handler(plugin_tracking_parameters.tracking_model_type, init=False)
    def _tracking_model_change():

        key = plugin_tracking_parameters.tracking_model_type.value
        select_model_skeleton(key)

    @change_handler(plugin.vollseg_model_type, init=False)
    def _seg_model_type_change(seg_model_type: Union[str, type]):
        selected = widget_for_vollseg_modeltype[seg_model_type]
        for w in {
            plugin.model_vollseg,
            plugin.model_vollseg_none,
            plugin.model_folder_vollseg,
        } - {selected}:
            w.hide()

        selected.show()

        # Trigger model change
        selected.changed(selected.value)

    @change_handler(plugin.model_vollseg, plugin.model_vollseg_none)
    def _seg_model_change(model_name: str):

        if Signal.sender() is not plugin.model_vollseg_none:

            model_class_vollseg = UNET
            key = model_class_vollseg, model_name

            if key not in model_vollseg_configs:

                @thread_worker
                def _get_model_folder():
                    return get_model_folder(*key)

                def _process_model_folder(path):

                    try:
                        model_vollseg_configs[key] = load_json(
                            str(path / "config.json")
                        )
                    finally:
                        select_model_vollseg(key)
                        plugin.progress_bar.hide()

                worker = _get_model_folder()
                worker.returned.connect(_process_model_folder)
                worker.start()

                # delay showing progress bar -> won't show up if model already downloaded
                # TODO: hacky -> better way to do this?
                time.sleep(0.1)
                plugin.call_button.enabled = False
                plugin.progress_bar.label = "Downloading UNET model"
                plugin.progress_bar.show()

            else:
                select_model_vollseg(key)

        else:
            select_model_vollseg(None)
            plugin.call_button.enabled = True
            plugin.model_folder_vollseg.line_edit.tooltip = (
                "Invalid model directory"
            )

    

    @change_handler(plugin.model_folder_vollseg, init=False)
    def _model_vollseg_folder_change(_path: str):
        path = Path(_path)
        key = CUSTOM_VOLLSEG, path
        try:
            if not path.is_dir():
                return
            model_vollseg_configs[key] = load_json(str(path / "config.json"))
        except FileNotFoundError:
            pass
        finally:
            select_model_vollseg(key)

   

    @change_handler(plugin.microscope_calibration_space)
    def _microscope_calibration_space(value: float):
        plugin.microscope_calibration_space.tooltip = (
            "Enter the pixel unit to real unit conversion for X"
        )
        plugin.microscope_calibration_space.value = value
       


    @change_handler(plugin.microscope_calibration_time)
    def _microscope_calibration_time(value: float):
        plugin.microscope_calibration_time.tooltip = (
            "Enter the pixel unit to real unit conversion for T"
        )
        plugin.microscope_calibration_time.value = value
        if plugin.image.value is not None:
            ndim = len(get_data(plugin.image.value).shape)


   
    @change_handler(plugin_tracking_parameters.defaults_params_button)
    def restore_prediction_parameters_defaults():
        for k, v in DEFAULTS_PRED_PARAMETERS.items():
            getattr(plugin_tracking_parameters, k).value = v

    @change_handler(plugin.defaults_model_button)
    def restore_model_defaults():
        for k, v in DEFAULTS_SEG_PARAMETERS.items():
            getattr(plugin, k).value = v

   

    @change_handler(plugin.recompute_current_button)
    def _recompute_current():

        pass
    # -> triggered by napari (if there are any open images on plugin launch)

    

    @change_handler(plugin.image, init=False)
    def _image_change(image: napari.layers.Image):
        plugin.image.tooltip = (
            f"Shape: {get_data(image).shape, str(image.name)}"
        )

        # dimensionality of selected model: 2, 3, or None (unknown)
        ndim = get_data(image).ndim
        ndim_model = ndim
        if (
            plugin.vollseg_model_type.value
            != DEFAULTS_MODEL["model_vollseg_none"]
        ):
            if model_selected_vollseg in model_vollseg_configs:
                config = model_vollseg_configs[model_selected_vollseg]
                ndim_model = config.get("n_dim")
        axes = None

        if ndim == 3:
            axes = "TYX"
            plugin.n_tiles.value = (1, 1, 1)
            plugin.recompute_current_button.show()
        elif ndim == 2 and ndim_model == 2:
            axes = "YX"
            plugin.n_tiles.value = (1, 1)
            plugin.recompute_current_button.hide()

        else:
            raise NotImplementedError()

        if axes == plugin.axes.value:
            # make sure to trigger a changed event, even if value didn't actually change
            plugin.axes.changed(axes)
        else:
            plugin.axes.value = axes
        plugin.n_tiles.changed(plugin.n_tiles.value)

    # -> triggered by _image_change
    @change_handler(plugin.axes, plugin.vollseg_model_type, init=False)
    def _axes_change():
        value = plugin.axes.value
        image = plugin.image.value
        axes = plugin.axes.value
        try:
            image is not None or _raise(ValueError("no image selected"))
            axes = axes_check_and_normalize(
                value, length=get_data(image).ndim, disallowed="S"
            )
            if (
                plugin.vollseg_model_type.value
                != DEFAULTS_MODEL["model_vollseg_none"]
            ):
                update_vollseg("image_axes", True, (axes, image, None))
        except ValueError as err:
            if (
                plugin.vollseg_model_type.value
                != DEFAULTS_MODEL["model_vollseg_none"]
            ):
                update_vollseg("image_axes", False, (value, image, err))
        # finally:
        # widgets_inactive(plugin.timelapse_opts, active=('T' in axes))

    # -> triggered by _image_change
    @change_handler(plugin.n_tiles, plugin.vollseg_model_type, init=False)
    def _n_tiles_change():
        image = plugin.image.value
        try:
            image is not None or _raise(ValueError("no image selected"))
            value = plugin.n_tiles.get_value()

            shape = get_data(image).shape
            try:
                value = tuple(value)
                len(value) == len(shape) or _raise(TypeError())
            except TypeError:
                raise ValueError(
                    f"must be a tuple/list of length {len(shape)}"
                )
            if not all(isinstance(t, int) and t >= 1 for t in value):
                raise ValueError("each value must be an integer >= 1")
            if (
                plugin.vollseg_model_type.value
                != DEFAULTS_MODEL["model_vollseg_none"]
            ):
                update_vollseg("n_tiles", True, (value, image, None))
        except (ValueError, SyntaxError) as err:
            if (
                plugin.vollseg_model_type.value
                != DEFAULTS_MODEL["model_vollseg_none"]
            ):
                update_vollseg("n_tiles", False, (None, image, err))

    # -------------------------------------------------------------------------

    return plugin
