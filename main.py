# -------------------------------------------------------------------------------
# Name:        Object bounding box label tool
# Purpose:     Label object bboxes for ImageNet Detection data
# Author:      Qiushi
# Created:     06/06/2014

#
# -------------------------------------------------------------------------------
from __future__ import division

import argparse
import json
from tkinter import *
from tkinter import ttk, messagebox

from PIL import Image, ImageTk
import os
import glob

parser = argparse.ArgumentParser(description="Object bounding box label tool")
parser.add_argument("--debug", type=str, default='', help="Enable debug mode or specify debug options")
args = parser.parse_args()

# colors for the bboxes
COLORS = {'person': 'red', 'object': 'blue'}


class LabelTool():
    def __init__(self, master):
        # set up the main frame
        self.parent = master
        self.parent.title("LabelTool")
        self.frame = Frame(self.parent)
        self.frame.pack(fill=BOTH, expand=1)
        self.parent.resizable(width=FALSE, height=FALSE)

        # initialize global state
        self.imageDir = ''
        self.imageList = []
        self.outDir = ''
        self.cur = 0
        self.total = 0
        self.category = 0
        self.imagename = ''
        self.labelfilename = ''
        self.tkimg = None

        # initialize mouse state
        self.STATE = {}
        self.STATE['click'] = 0
        self.STATE['x'], self.STATE['y'] = 0, 0
        self.STATE['label_type'] = 'person'  # To store the type of label (Person/Object)

        # reference to bbox
        self.bboxIdList = []
        self.bboxId = None
        self.bboxList = []
        self.bboxTypes = []  # To store type information for bboxes
        self.hl = None
        self.vl = None

        # Connection management
        self.connectionLines = []
        self.selected_indices = []  # To store selected indices for connections
        self.connections = []  # To store connections

        # ----------------- GUI stuff ---------------------
        # dir entry & load
        self.label = Label(self.frame, text="Image Dir:")
        self.label.grid(row=0, column=0, sticky=E)
        self.entry = Entry(self.frame)
        self.entry.grid(row=0, column=1, sticky=W + E)
        self.ldBtn = Button(self.frame, text="Load", command=self.loadDir)
        self.ldBtn.grid(row=0, column=2, sticky=W + E)

        # Scrollable main panel for labeling
        self.canvasFrame = Frame(self.frame)
        self.canvasFrame.grid(row=1, column=1, rowspan=4, sticky=N + E + S + W)

        self.mainPanel = Canvas(self.canvasFrame, cursor='tcross')
        self.scrollY = Scrollbar(self.canvasFrame, orient=VERTICAL, command=self.mainPanel.yview)
        self.scrollX = Scrollbar(self.canvasFrame, orient=HORIZONTAL, command=self.mainPanel.xview)

        self.mainPanel.config(yscrollcommand=self.scrollY.set, xscrollcommand=self.scrollX.set)

        self.scrollY.pack(side=RIGHT, fill=Y)
        self.scrollX.pack(side=BOTTOM, fill=X)
        self.mainPanel.pack(side=LEFT, fill=BOTH, expand=True)

        self.mainPanel.bind("<Button-1>", self.mouseClick)
        self.mainPanel.bind("<Motion>", self.mouseMove)
        self.parent.bind("<Escape>", self.cancelBBox)  # press <Escape> to cancel current bbox
        self.parent.bind("s", self.cancelBBox)
        self.parent.bind("a", self.prevImage)  # press 'a' to go backward
        self.parent.bind("f", self.nextImage)  # press 'f' to go forward
        self.parent.bind("t", self.nextWithAnnotationsImage) # press 't' to move annotation to next image
        self.parent.bind("v", self.nextRelabelImage)
        self.parent.bind("q", self.toggle_drag_mode)


        # showing bbox info & delete bbox &
        self.lb1 = Label(self.frame, text='Bounding boxes:')
        self.lb1.grid(row=1, column=2, sticky=W + N)
        self.listbox = Listbox(self.frame, width=22, height=12)
        self.listbox.grid(row=2, column=2, sticky=N + S)  # Resizable height, fixed width
        self.btnDel = Button(self.frame, text='Delete Object', command=self.delBBox)
        self.btnDel.grid(row=3, column=2, sticky=W + E + N)
        self.btnClear = Button(self.frame, text='ClearAll', command=self.clear_all_btn)
        self.btnClear.grid(row=4, column=2, sticky=W + E + N)
        self.frame.grid_rowconfigure(2, weight=1)  # Make row 2 resizable
        self.frame.grid_columnconfigure(2, weight=0, minsize=150)  # Fixed width

        # control panel for bounding box type selection
        self.typePanel = Frame(self.frame)
        self.typePanel.grid(row=1, column=3, sticky=N + W)

        # person button
        self.personBtn = Button(self.typePanel, text='Person', command=lambda: self.setLabelType('person'))
        self.personBtn.pack(side=TOP, pady=5)

        # object selection
        self.objectOptions = (
                ['cell phone'] +
                ['cup', 'bottle'] +
                ['couch'] +
                ['apple'] +
                ['book'] +
                ['laptop']
        )
        self.objectOptions.sort()
        self.objectDropdown = ttk.OptionMenu(
            self.typePanel, StringVar(value='Object'), None, *self.objectOptions, command=self.setObjectType
        )
        self.objectDropdown.pack(side=TOP, pady=5)

        # Add connection buttons
        self.connectBtn = Button(self.typePanel, text='Select for \nConnection', command=self.selectForConnection)
        self.connectBtn.pack(side=TOP, pady=5)

        self.connectionOptions = (['no_interaction', 'hold'] +
                                  ['talk_on', 'text_on'] +
                                  ['drink_with'] +
                                  ['lie_on', 'sit_on'] +
                                  ['eat'] + # hold
                                  ['read'] + # hold -> erstmal nicht labeln
                                  ['type_on'] # hold
        )
        self.connectionOptions.sort()
        self.connectionDropdown = ttk.OptionMenu(
            self.typePanel, StringVar(value='Save Connection'), None, *self.connectionOptions,
            command=self.save_connection
        )
        self.connectionDropdown.pack(side=TOP, pady=5)

        # control panel for image navigation
        self.ctrPanel = Frame(self.frame)
        self.ctrPanel.grid(row=5, column=1, columnspan=2, sticky=W + E)
        self.prevBtn = Button(self.ctrPanel, text='<< Prev', width=10, command=self.prevImage)
        self.prevBtn.pack(side=LEFT, padx=5, pady=3)
        self.nextBtn = Button(self.ctrPanel, text='Next >>', width=10, command=self.nextImage)
        self.nextBtn.pack(side=LEFT, padx=5, pady=3)
        self.progLabel = Label(self.ctrPanel, text="Progress:     /    ")
        self.progLabel.pack(side=LEFT, padx=5)
        self.tmpLabel = Label(self.ctrPanel, text="Go to Image No.")
        self.tmpLabel.pack(side=LEFT, padx=5)
        self.idxEntry = Entry(self.ctrPanel, width=5)
        self.idxEntry.pack(side=LEFT)
        self.goBtn = Button(self.ctrPanel, text='Go', command=self.gotoImage)
        self.goBtn.pack(side=LEFT)

        self.nextWithAnnotationsBtn = Button(self.ctrPanel, text='Next wA >>', width=10,
                                             command=self.nextWithAnnotationsImage)
        self.nextWithAnnotationsBtn.pack(side=LEFT, padx=5, pady=3)

        self.nextRelabelBtn = Button(self.ctrPanel, text='Next relabel >>', width=10, command=self.nextRelabelImage)
        self.nextRelabelBtn.pack(side=LEFT, padx=5, pady=3)

        # display mouse position
        self.disp = Label(self.ctrPanel, text='')
        self.disp.pack(side=RIGHT)

        self.frame.columnconfigure(1, weight=1)
        self.frame.rowconfigure(1, weight=1)

        # showing connection info & delete connection
        self.lbConnections = Label(self.frame, text='Connections:')
        self.lbConnections.grid(row=1, column=4, sticky=W + N)
        self.connectionListbox = Listbox(self.frame, width=22, height=12)
        self.connectionListbox.grid(row=2, column=4, sticky=N + S)
        self.delConnectionBtn = Button(self.frame, text='Delete Connection', command=self.delConnection)
        self.delConnectionBtn.grid(row=3, column=4, sticky=W + E + N)
        self.frame.grid_columnconfigure(4, weight=0, minsize=150)  # Fixed width for connections column

        self.del_all_connections_btn = Button(self.frame, text='Delete All Connections', command=self.clear_all_connections)
        self.del_all_connections_btn.grid(row=4, column=4, sticky=W + E + N)

        # Display filename
        self.filenameLabel = Label(self.ctrPanel, text="Filename: ", anchor=W)
        self.filenameLabel.pack(side=LEFT, padx=5)

        # Initialize dragging state and mode toggle
        self.drag_mode = False
        self.drag_data = {"x": 0, "y": 0, "item": None}

        # Add "Move BBox" button to toggle dragging mode
        self.moveModeBtn = Button(self.ctrPanel, text="Move BBox", command=self.toggle_drag_mode)
        self.moveModeBtn.pack(side=LEFT, padx=5, pady=3)

        # Updated mouse bindings
        self.mainPanel.bind("<ButtonPress-1>", self.mouseClick)
        self.mainPanel.bind("<B1-Motion>", self.on_drag_motion)
        self.mainPanel.bind("<ButtonRelease-1>", self.on_drag_end)

        # images resizing
        self.resize_mode = False
        self.resize_data = {"x": 0, "y": 0, "item": None, "corner": None}
        self.resize_threshold = 10  # Pixels

    def selectForConnection(self):
        sel = self.listbox.curselection()
        if len(sel) != 1:
            print("Please select exactly one bounding box.")
            return

        idx = int(sel[0])
        if idx in self.selected_indices:
            bbox_id = self.bboxIdList[idx]
            self.mainPanel.itemconfig(bbox_id, fill="", stipple="")  # Adjust color and transparency
            self.selected_indices.remove(idx)
            return

        if len(sel) != 1 or len(self.selected_indices) == 2:
            return

        self.selected_indices.append(idx)
        # Apply high transparency color to the rectangle
        bbox_id = self.bboxIdList[idx]
        self.mainPanel.itemconfig(bbox_id, fill="blue", stipple="gray50")  # Adjust color and transparency

    def save_connection(self, connection_type):
        if len(self.selected_indices) == 2:
            for bbox_id in self.bboxIdList:
                self.mainPanel.itemconfig(bbox_id, fill="", stipple="")

            sub, obj = self.selected_indices

            # Draw the connection line
            center1 = self.getBBoxCenter(self.bboxList[sub])
            center2 = self.getBBoxCenter(self.bboxList[obj])
            line_id = self.mainPanel.create_line(
                center1[0], center1[1], center2[0], center2[1], fill="yellow", width=2
            )
            self.connectionLines.append(line_id)

            # Add to connections and connectionListbox
            connection = {
                "object_id": obj,
                "interaction": connection_type,
                "subject_id": sub
            }

            self.connections.append(connection)
            self.connectionListbox.insert(END, f"[{sub} - {connection_type} - {obj}]")

            self.STATE['connection'] = None
            self.selected_indices = []

    def delConnection(self):
        sel = self.connectionListbox.curselection()
        if len(sel) != 1:
            print("Please select exactly one connection to delete.")
            return
        idx = int(sel[0])

        # Remove the connection line from the canvas
        self.mainPanel.delete(self.connectionLines[idx])
        self.connectionLines.pop(idx)

        # Remove the connection from the data and listbox
        self.connections.pop(idx)
        self.connectionListbox.delete(idx)

    def getBBoxCenter(self, bbox):
        """
        Helper function to calculate the center of a bounding box.
        :param bbox: A tuple (x1, y1, x2, y2) representing the bounding box.
        :return: A tuple (x_center, y_center).
        """
        x1, y1, x2, y2 = bbox
        x_center = (x1 + x2) / 2
        y_center = (y1 + y2) / 2
        return x_center, y_center

    def loadDir(self):
        if args.debug:
            image_directory = args.debug
        else:
            image_directory = self.entry.get()
            self.parent.focus()

        self.imageDir = image_directory
        self.imageList = glob.glob(os.path.join(self.imageDir, '*.png'))
        self.imageList.sort()
        if len(self.imageList) == 0:
            print('No .png images found in the specified dir!')
            return

        # default to the 1st image in the collection
        self.cur = 1
        self.total = len(self.imageList)

        # set up output dir
        if self.imageDir.startswith("Images"):
            self.outDir = self.imageDir.replace("Images", "Labels", 1)
        else:
            self.outDir = "Labels"

        print(self.outDir)
        if not os.path.exists(self.outDir):
            os.mkdir(self.outDir)

        self.loadImage()

    def loadImage(self, prev=False, relabel=False):
        # load image
        imagepath = self.imageList[self.cur - 1]
        self.img = Image.open(imagepath)
        self.tkimg = ImageTk.PhotoImage(self.img)

        # Update canvas size to match image dimensions
        self.mainPanel.config(scrollregion=(0, 0, self.tkimg.width(), self.tkimg.height()))
        self.mainPanel.create_image(0, 0, image=self.tkimg, anchor=NW)
        self.progLabel.config(text="%04d/%04d" % (self.cur, self.total))

        # Update filename label
        self.imagename = os.path.split(imagepath)[-1]
        self.filenameLabel.config(text=f"Filename: {self.imagename}")

        # load labels
        self.clear_all()
        self.imagename = os.path.split(imagepath)[-1]
        image_name_without_extension = os.path.split(imagepath)[-1].split('.')[0]
        labelname = image_name_without_extension + '.txt'
        self.labelfilename = os.path.join(self.outDir, labelname)

        if prev or relabel:
            prev_image_path = self.imageList[self.cur - 2]
            prev_image_name_without_extension = os.path.split(prev_image_path)[-1].split('.')[0]
            prev_label_name = prev_image_name_without_extension + '.txt'
            prev_label_file_name = os.path.join(self.outDir, prev_label_name)
            load_filename = prev_label_file_name
        else:
            load_filename = self.labelfilename

        if not os.path.exists(load_filename):
            return

        with open(load_filename, 'r') as file:
            data = json.load(file)

        if relabel:
            with open(self.labelfilename, 'r') as file:
                data_person = json.load(file)

            gtbox = data_person["gtboxes"][0]

            x1, y1, width, height = map(int, gtbox["box"])
            x2, y2 = x1 + width - 1, y1 + height - 1
            self.bboxList.append((x1, y1, x2, y2))
            label_type = gtbox["tag"]
            self.bboxTypes.append(label_type)
            tmpId = self.mainPanel.create_rectangle(
                x1, y1, x2, y2, width=2, outline=COLORS[label_type if label_type == 'person' else 'object']
            )
            self.bboxIdList.append(tmpId)
            self.listbox.insert(END, f'[{0}][{label_type}]')
            # self.listbox.insert(END, f'[{x1} {y1} {x2} {y2}]')
            self.listbox.itemconfig(len(self.bboxIdList) - 1,
                                    fg=COLORS[label_type if label_type == 'person' else 'object'])

            for index, gtbox in enumerate(data["gtboxes"]):
                if index == 0:
                    continue

                x1, y1, width, height = map(int, gtbox["box"])
                x2, y2 = x1 + width - 1, y1 + height - 1
                self.bboxList.append((x1, y1, x2, y2))
                label_type = gtbox["tag"]
                self.bboxTypes.append(label_type)
                tmpId = self.mainPanel.create_rectangle(
                    x1, y1, x2, y2, width=2, outline=COLORS[label_type if label_type == 'person' else 'object']
                )
                self.bboxIdList.append(tmpId)
                self.listbox.insert(END, f'[{index}][{label_type}]')
                # self.listbox.insert(END, f'[{x1} {y1} {x2} {y2}]')
                self.listbox.itemconfig(len(self.bboxIdList) - 1,
                                        fg=COLORS[label_type if label_type == 'person' else 'object'])

        else:
            # load bounding boxes
            for index, gtbox in enumerate(data["gtboxes"]):
                x1, y1, width, height = map(int, gtbox["box"])
                x2, y2 = x1 + width - 1, y1 + height - 1
                self.bboxList.append((x1, y1, x2, y2))
                label_type = gtbox["tag"]
                self.bboxTypes.append(label_type)
                tmpId = self.mainPanel.create_rectangle(
                    x1, y1, x2, y2, width=2, outline=COLORS[label_type if label_type == 'person' else 'object']
                )
                self.bboxIdList.append(tmpId)
                self.listbox.insert(END, f'[{index}][{label_type}]')
                # self.listbox.insert(END, f'[{x1} {y1} {x2} {y2}]')
                self.listbox.itemconfig(len(self.bboxIdList) - 1,
                                        fg=COLORS[label_type if label_type == 'person' else 'object'])

        # loading connections
        for conn in data["hoi"]:
            sub = conn['subject_id']
            obj = conn['object_id']
            interaction = conn['interaction']

            center1 = self.getBBoxCenter(self.bboxList[sub])
            center2 = self.getBBoxCenter(self.bboxList[obj])

            line_id = self.mainPanel.create_line(
                center1[0], center1[1], center2[0], center2[1], fill="yellow", width=2
            )
            self.connectionLines.append(line_id)  # Track connection line

            connection = {
                "object_id": obj,
                "interaction": interaction,
                "subject_id": sub
            }
            self.connections.append(connection)
            self.connectionListbox.insert(END, f"[{sub} - {interaction} - {obj}]")

        print("-----------------------------------------------------------")
        print(f"conn: {self.connections}")

    def saveImage(self):
        # if len(self.connections) == 0 and len(self.bboxList) == 0:
        #     return

        if len(self.connections) == 0:
            conn = []

            if len(self.bboxTypes) != 0 and self.bboxTypes[0] == 'person':
                for index, _ in enumerate(self.bboxList[1:], start=1):
                    conn.append(
                        {
                            "object_id": index,
                            "interaction": "no_interaction",
                            "subject_id": 0
                        }
                    )
        else:
            conn = self.connections


        data = {
            "file_name": self.imagename,
            "height": self.img.height,
            "width": self.img.width,
            "gtboxes": [
                {
                    "tag": self.bboxTypes[i],
                    "box": [int(x_min), int(y_min), int(width), int(height)]
                }
                for i, bbox in enumerate(self.bboxList)
                for x_min, y_min, x_max, y_max in [bbox]
                for width, height in [(x_max - x_min + 1, y_max - y_min + 1)]
            ],
            "hoi": conn
        }

        print(f"saved data: {data}")
        with open(self.labelfilename, 'w') as f:
            json.dump(data, f)

        # print('Image No. %d saved' % self.cur)

    def setLabelType(self, label_type):
        self.STATE['label_type'] = label_type

    def setObjectType(self, selection):
        self.STATE['label_type'] = selection

    def mouseMove(self, event):
        # Calculate the scroll offset
        x_offset = self.mainPanel.canvasx(event.x)
        y_offset = self.mainPanel.canvasy(event.y)

        # Update the mouse position display
        self.disp.config(text=f'x: {x_offset:.0f}, y: {y_offset:.0f}')

        if self.tkimg:
            # Update horizontal line
            if self.hl:
                self.mainPanel.delete(self.hl)
            self.hl = self.mainPanel.create_line(0, y_offset, self.tkimg.width(), y_offset, width=2)

            # Update vertical line
            if self.vl:
                self.mainPanel.delete(self.vl)
            self.vl = self.mainPanel.create_line(x_offset, 0, x_offset, self.tkimg.height(), width=2)

        # Update bounding box preview
        if self.STATE['click'] == 1:
            if self.bboxId:
                self.mainPanel.delete(self.bboxId)
            self.bboxId = self.mainPanel.create_rectangle(
                self.STATE['x'], self.STATE['y'], x_offset, y_offset,
                width=2,
                outline=COLORS[self.STATE['label_type'] if self.STATE['label_type'] == 'person' else 'object']
            )

    def mouseClick(self, event):
        x_offset = int(self.mainPanel.canvasx(event.x))
        y_offset = int(self.mainPanel.canvasy(event.y))

        if self.drag_mode:
            sel = self.listbox.curselection()
            if len(sel) != 1:
                for bbox_id in self.bboxIdList:
                    coords = self.mainPanel.coords(bbox_id)
                    x1, y1, x2, y2 = coords

                    # Check if the click is near any corner
                    corners = {
                        "top_left": (x1, y1),
                        "top_right": (x2, y1),
                        "bottom_left": (x1, y2),
                        "bottom_right": (x2, y2)
                    }

                    for corner_name, (cx, cy) in corners.items():
                        if abs(cx - x_offset) <= self.resize_threshold and abs(cy - y_offset) <= self.resize_threshold:
                            # Start resizing
                            self.resize_mode = True
                            self.resize_data = {"x": x_offset, "y": y_offset, "item": bbox_id, "corner": corner_name}
                            return

                    # Start dragging if click is within the rectangle
                    if x1 <= x_offset <= x2 and y1 <= y_offset <= y2:
                        self.drag_data["item"] = bbox_id
                        self.drag_data["x"] = x_offset
                        self.drag_data["y"] = y_offset
                        return
            else:
                idx = int(sel[0])
                self.drag_data["item"] = self.bboxIdList[idx]
                self.drag_data["x"] = x_offset
                self.drag_data["y"] = y_offset
                return

        else:
            # If not in drag mode, handle drawing a new rectangle
            if self.STATE['click'] == 0:
                self.STATE['x'], self.STATE['y'] = x_offset, y_offset
                self.STATE['click'] = 1
            else:
                x1, x2 = min(self.STATE['x'], x_offset), max(self.STATE['x'], x_offset)
                y1, y2 = min(self.STATE['y'], y_offset), max(self.STATE['y'], y_offset)
                self.bboxList.append((x1, y1, x2, y2))
                self.bboxTypes.append(self.STATE['label_type'])  # Default to the current label type
                self.bboxIdList.append(self.bboxId)
                self.bboxId = None
                self.listbox.insert(END, f'[{len(self.bboxList) - 1}][{self.STATE["label_type"]}]')
                self.listbox.itemconfig(
                    len(self.bboxIdList) - 1,
                    fg=COLORS[self.STATE['label_type'] if self.STATE['label_type'] == 'person' else 'object']
                )
                self.STATE['click'] = 0

                # Show the pop-up for label selection
                self.show_label_selection_popup()

    def cancelBBox(self, event):
        if 1 == self.STATE['click']:
            if self.bboxId:
                self.mainPanel.delete(self.bboxId)
                self.bboxId = None
                self.STATE['click'] = 0

    def delBBox(self):
        sel = self.listbox.curselection()
        if len(sel) != 1:
            return
        idx = int(sel[0])
        self.mainPanel.delete(self.bboxIdList[idx])
        self.bboxIdList.pop(idx)
        self.bboxList.pop(idx)
        self.bboxTypes.pop(idx)
        self.listbox.delete(idx)

    def clear_all_btn(self):
        # Show a confirmation dialog before clearing
        confirm = messagebox.askyesno("Confirmation", "Are you sure you want to clear all bounding boxes?")
        if not confirm:
            return

        self.clear_all()

    def clear_all(self):
        # empty bboxes
        self.bboxTypes = []

        # Clear bounding boxes
        for idx in range(len(self.bboxIdList)):
            self.mainPanel.delete(self.bboxIdList[idx])
        self.listbox.delete(0, len(self.bboxList))
        self.bboxIdList = []
        self.bboxList = []

        # Clear connections
        self.clear_all_connections()


    def clear_all_connections(self):
        for line in self.connectionLines:
            self.mainPanel.delete(line)
        self.connectionLines = []
        self.connectionListbox.delete(0, len(self.connections))
        self.connections = []

    def prevImage(self, event=None):
        self.saveImage()
        if self.cur > 1:
            self.cur -= 1
            self.loadImage()

    def nextImage(self, event=None):
        self.saveImage()
        if self.cur < self.total:
            self.cur += 1
            self.loadImage()

    def nextWithAnnotationsImage(self, event=None):
        self.saveImage()
        if self.cur < self.total:
            self.cur += 1
            self.loadImage(prev=True)

    def nextRelabelImage(self, event=None):
        self.saveImage()
        if self.cur < self.total:
            self.cur += 1
            self.loadImage(relabel=True)

    def gotoImage(self):
        idx = int(self.idxEntry.get())
        if 1 <= idx <= self.total:
            self.saveImage()
            self.cur = idx
            self.loadImage()

        self.parent.focus()

    def toggle_drag_mode(self, event=None):
        """Toggle the drag mode."""
        self.drag_mode = not self.drag_mode
        if self.drag_mode:
            self.moveModeBtn.config(relief=SUNKEN, text="Drag Mode: ON")
        else:
            self.moveModeBtn.config(relief=RAISED, text="Move BBox")

    def on_drag_motion(self, event):
        x, y = self.mainPanel.canvasx(event.x), self.mainPanel.canvasy(event.y)

        if self.resize_mode and self.resize_data["item"] is not None:
            item_index = self.bboxIdList.index(self.resize_data["item"])
            x1, y1, x2, y2 = self.mainPanel.coords(self.resize_data["item"])

            # Update coordinates based on the corner being dragged
            corner = self.resize_data["corner"]
            if corner == "top_left":
                x1, y1 = x, y
            elif corner == "top_right":
                x2, y1 = x, y
            elif corner == "bottom_left":
                x1, y2 = x, y
            elif corner == "bottom_right":
                x2, y2 = x, y

            # Update the rectangle on the canvas
            self.mainPanel.coords(self.resize_data["item"], x1, y1, x2, y2)

            # Update bounding box list
            self.bboxList[item_index] = (x1, y1, x2, y2)

        elif self.drag_data["item"] is not None:
            dx, dy = x - self.drag_data["x"], y - self.drag_data["y"]

            # Move the rectangle
            self.mainPanel.move(self.drag_data["item"], dx, dy)

            # Update the drag data
            self.drag_data["x"] = x
            self.drag_data["y"] = y

    def on_drag_end(self, event):
        if self.resize_mode:
            self.resize_mode = False
            self.resize_data = {"x": 0, "y": 0, "item": None, "corner": None}
        elif self.drag_data["item"] is not None:
            x1, y1, x2, y2 = self.mainPanel.coords(self.drag_data["item"])
            item_index = self.bboxIdList.index(self.drag_data["item"])
            self.bboxList[item_index] = (x1, y1, x2, y2)

            self.listbox.delete(item_index)
            self.listbox.insert(item_index, f'[{item_index}][{self.bboxTypes[item_index]}]')
            self.listbox.itemconfig(
                item_index,
                fg=COLORS[self.bboxTypes[item_index] if self.bboxTypes[item_index] == 'person' else 'object']
            )
            self.drag_data = {"x": 0, "y": 0, "item": None}

    def show_label_selection_popup(self):
        popup = Toplevel(self.parent)
        popup.title("Select Label")
        popup.geometry("200x400")

        label_var = StringVar(value=self.STATE['label_type'])

        Label(popup, text="Choose a label:").pack(pady=10)

        # Add radio buttons for label selection
        for label in ['person'] + self.objectOptions:
            Radiobutton(popup, text=label, variable=label_var, value=label).pack(anchor=W)

        Button(popup, text="OK", command=lambda: self.set_label_from_popup(popup, label_var)).pack(pady=10)

    def set_label_from_popup(self, popup, label_var):
        selected_label = label_var.get()
        self.STATE['label_type'] = selected_label
        self.bboxTypes[-1] = selected_label  # Update the last bounding box's type
        self.listbox.delete(len(self.bboxList) - 1)  # Remove and re-add the last bbox entry
        self.listbox.insert(END, f'[{len(self.bboxList) - 1}][{selected_label}]')
        self.listbox.itemconfig(
            len(self.bboxIdList) - 1,
            fg=COLORS[selected_label if selected_label == 'person' else 'object']
        )
        popup.destroy()


if __name__ == '__main__':
    root = Tk()
    tool = LabelTool(root)
    root.resizable(width=True, height=True)
    root.mainloop()
