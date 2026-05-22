# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Clickpointtoedit
                                 A QGIS plugin
 Clickpointtoedit
 Create Plugin By: https://github.com/Genroy
                              -------------------
        begin                : 2025-05-01
        git sha              : $Format:%H$
        copyright            : (C) 2025 by Thamoon Kedkaew (CeJ)
        Author               : Thamoon Kedkaew (CeJ)
        email                : pongsakornche@gmail.com
 ***************************************************************************/
"""

from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt, pyqtSignal
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QAction, QDockWidget, QPushButton, QVBoxLayout, QFormLayout, QLineEdit,
    QMessageBox, QWidget, QScrollArea, QFileDialog, QLabel, QHBoxLayout,
    QComboBox, QDialog, QListWidget, QListWidgetItem, QSizePolicy
)
from qgis.gui import QgsMapToolIdentifyFeature, QgsHighlight
from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsFeatureRequest
from PyQt5.QtCore import QVariant
import os.path
import csv
from datetime import datetime
import codecs


class CustomIdentifyTool(QgsMapToolIdentifyFeature):
    feature_clicked = pyqtSignal(object)

    def __init__(self, canvas, layer):
        super().__init__(canvas)
        self.canvas = canvas
        self._layer = layer
        self.setLayer(layer)

    def canvasReleaseEvent(self, event):
        results = self.identify(event.x(), event.y(), [self._layer], self.TopDownStopAtFirst)
        if results:
            feature = results[0].mFeature
            self.feature_clicked.emit(feature)


# --------- ป้องกันคอมโบเปลี่ยนค่าด้วยล้อเมาส์ถ้ายังไม่เปิด popup ----------
class NoScrollComboBox(QComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._popup_open = False
        self.setFocusPolicy(Qt.StrongFocus)

    def showPopup(self):
        self._popup_open = True
        super().showPopup()

    def hidePopup(self):
        super().hidePopup()
        self._popup_open = False

    def wheelEvent(self, event):
        if self._popup_open:
            super().wheelEvent(event)
        else:
            event.ignore()


class Clickpointtoedit:
    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = self.tr(u'&Clickpointtoedit')
        self.first_start = None
        self.tool = None
        self.dock = None
        self.fields = []  # (field_name, widget)
        self.highlight = None           # last red highlight
        self.saved_highlights = []      # keep green highlights until export
        self.action = None

        self.help_dock = None  # help dock widget

        # --- UI constants (Small: กระทัดรัด) ---
        self.UI_MIN_WIDTH     = 240
        self.UI_CTRL_HEIGHT   = 28
        self.TYPE_BADGE_MIN_W = 90
        self.UI_DOCK_MIN_W    = 380
        self.UI_DOCK_MAX_W    = 520
        self.UI_DOCK_PREF_W   = 460
        self.UI_DOCK_PREF_H   = 360

        # === Mapping ===
        self.bl_owner_map = {"1 = รัฐ": 1, "2 = เอกชน": 2, "3 = กรุงเทพมหานคร": 3}
        self.bl_owner_reverse_map = {v: k for k, v in self.bl_owner_map.items()}

        self.bl_area_flag_map = {"C = การคำนวณ": "C", "F = การวัดในพื้นที่": "F", "P = ผังบริเวณ": "P"}
        self.bl_area_flag_reverse_map = {v: k for k, v in self.bl_area_flag_map.items()}

        self.bl_type_map = {
            "1 = บ้านเดี่ยว / อาคารเดี่ยว": 1,
            "2 = บ้านแฝด": 2,
            "3 = ทาวเฮ้าส์": 3,
            "4 = ห้องแถว (ไม้ สังกะสี กระเบื้อง)": 4,
            "5 = ตึกแถว / อาคารครึ่งตึกครึ่งไม้": 5,
            "6 = อาคารที่ใช้ในการพักอาศัยถาวรและชั่วคราว เช่นโรงแรม แฟตร หอพัก อาคารชุด แมนชั่น เกสต์เฮ้าส์": 6,
            "7 = เรือนแพ": 7,
            "8 = เพิงกึ่งถาวร": 8,
            "98 = อื่น ๆ": 98,
            "99 = ไม่ทราบ": 99
        }
        self.bl_type_reverse_map = {v: k for k, v in self.bl_type_map.items()}

        self.bl_use_map = {
            "1000 = ที่อยู่อาศัย": 1000,
            "1100 = ที่พักอาศัย (บ้าน หอพัก อาคารชุดเพื่อการอยู่อาศัย โฮมสเตย์ คอนโดมิเนียม บ้านพักครูเอกชน) = 1100": 1100,
            "1102 = บ้านพักพนักงานบริษัทพานิชยกรรม = 1102": 1102,
            "1103 = บ้านพักพนักงานในอุตสาหกรรม": 1103,
            "1105 = บ้านพักพนักงานรัฐวิสาหกิจ": 1105,
            "1106 = หอพักนักเรียน / นักศึกษา": 1106,
            "1200 = วัง ตำหนัก และที่พระราชฐาน": 1200,
            "1300 = บ้านพักข้าราชการ": 1300,
            "1600 = อนุรักษ์เพื่อการอยู่อาศัย": 1600,
            "1800 = ที่อยู่อาศัยอื่น ๆ หรืออาคารประกอบการพักอาศัย": 1800,
            "2000 = พาณิชยกรรม": 2000,
            "2100 = สำนักงานและบริษัท โชว์ รูมรถที่ไม่มีบริการซ่อม": 2100,
            "2200 = ธุรกิจบริการ": 2200,
            "2210 = ตลาด": 2210,
            "2220 = โรงแรม บังกะโล รีสอร์ท เกสต์เฮ้าส์": 2220,
            "2230 = ห้างสรรพสินค้า": 2230,
            "2231 = ศูนย์รวมวัสดุก่อสร้างและของแต่งบ้าน": 2231,
            "2232 = ศูนย์การค้าละแวกบ้าน (COMMUNITY MALL)": 2232,
            "2233 = มินิมาร์ท (MINIMART)": 2233,
            "2240 = สถานีบริการเชื้อเพลิง ปั๊มน้ำมัน ปั๊มแก๊ส และปั๊มหลอด": 2240,
            "2259 = ร้านขายแก๊ส ธุรกิจบริการแก๊ส": 2250,
            "2260 = สถาบันสอนคอมพิวเตอร์ กวดวิชา สอนภาษา สอนดนตรี สอนการแสดง สอนศิลปะป้องกันตัว": 2260,
            "2270 = ธุรกิจประกันภัย ประกันชีวิต (สำนักงาน)": 2270,
            "2280 = ธุรกิจบริการอื่น ๆ": 2280,
            "2300 = ธนาคารและสถาบันการเงิน": 2300,
            "2301 = ธนาคาร สถาบันการเงิน": 2301,
            "2302 = ลิสซิ่ง โรงรับจำนำ(เอกชน) ธุรกิจการเงินอื่น ๆ": 2302,
            "2400 = ธุรกิจนันทนาการ": 2400,
            "2410 = โรงภาพยนตร์ โรงละคร และโรงมโหรสพอื่น": 2410,
            "2420 = ไนต์คลับ คาราโอเกะ คาเฟ่ อาบอบนวด ผับ บาร์เบียร์": 2420,
            "2480 = ธุรกิจนันทนาการอื่น ๆ": 2480,
            "2800 = พาณิชยกรรมอื่น ๆ": 2800,
            "3000 = อุตสาหกรรม": 3000,
            "3100 = อุตสาหกรรม": 3100,
            "3110 = โรงงาน": 3110,
            "3120 = โรงฆ่าสัตว์": 3120,
            "3130 = อุตสาหกรรมที่เป็นอันตราย": 3130,
            "3140 = อุตสาหกรรมชุมชน": 3140,
            "3300 = คลังสินค้า": 3300,
            "3310 = ไซโลเก็บผลผลิตทางการเกษตร": 3310,
            "3320 = คลังน้ำมัน คลังแก๊ส คลังเก็บวัตถุอันตราย": 3320,
            "3400 = อุตสาหกรรมเฉพาะกิจ": 3400,
            "3800 = อุตสาหกรรมอื่น": 3800,
            "4000 = การใช้ประโยชน์แบบผสม": 4000,
            "4100 = ที่พักอาศัยกึ่งพาณิชยกรรม": 4100,
            "4110 = ที่พักอาศัยกึ่งอาคารสำนักงาน": 4110,
            "4120 = ที่พักอาศัยกึ่งธุรกิจบริการ": 4120,
            "4121 = ร้านค้าวัสดุก่อสร้าง": 4121,
            "4122 = ร้านขายทอง เครื่องประดับอัญมณี": 4122,
            "4123 = ร้านซื้อขายหรือเก็บเศษวัสดุ": 4123,
            "4180 = ที่พักอาศัยกึ่งเกษตรกรรม": 4180,
            "4200 = พาณิชยกรรมและอุตสาหกรรม": 4200,
            "4300 = ที่พักอาศัยกึ่งอุตสาหกรรม": 4300,
            "5000 = สาธารณูปโภค": 5000,
            "5130 = ท่าอากาศยาน": 5130,
            "5140 = ท่าเรือ": 5140,
            "5150 = สถานีขนส่ง ท่ารถประจำท้องถิ่น ท่ารถเมล์": 5150,
            "5160 = สถานีรถไฟ": 5160,
            "5180 = สถานีคมนาคมและขนส่งอื่น ๆ คลังสินค้า ศูนย์กระจายสินค้า จุดพักรถ(ขนส่งสินค้าและแวะพักรถ)": 5180,
            "5200 = โทรศัพท์": 5200,
	        "5210 = ที่ทำการโทรศัพท์": 5210,
	        "5220 = ชุมสายโทรศัพท์": 5220,
	        "5230 = ที่ทำการและชุมสายโทรศัพท์": 5230,
	        "5300 = ไฟฟ้า": 5300,
	        "5130 = ที่ทำการไฟฟ้า": 5130,
	        "5120 = สถานีย่อยไฟฟ้า": 5120,
	        "5130 = ที่ทำการและสถานีย่อยไฟฟ้า": 5330,
	        "5400 = ประปา": 5400,
	        "5410 = ที่ทำการประปา": 5410,
	        "5420 = สถานีสูบน้ำ โรงกรองน้ำ": 5420,
	        "5430 = ที่ทำการและสถานีย่อยประปา": 5430,
	        "5440 = ระบบประปาหมู่บ้าน": 5440,
	        "5500 = รักษาคุณภาพและสิ่งแวดล้อม": 5500,
	        "5510 = การจัดเก็บและกำจัดขยะ": 5510,
	        "5520 = การระบายน้ำและบำบัดน้ำเสีย": 5520,
	        "5800 = สาธารณูปโภคอื่น ๆ (สถานีวิทยุโทรทัศน์ สถานีวิทยุกระจายเสียง ศาลารอรถ)": 5800,
	        "6000 = สาธารณูปการ": 6000,
	        "6100 = สถาบันการศึกษา": 6100,
	        "6105 = ศูนย์พัฒนาเด็กเล็ก สถานรับเลี้ยงเด็กก่อนเกณฑ์": 6105,
	        "6110 = โรงเรียนอนุบาล": 6110,
	        "6121 = โรงเรียนประถมศึกษา": 6121,
	        "6130 = โรงเรียนมัธยมศึกษา": 6130,
	        "6140 = โรงเรียนที่มีระดับการศึกษาแบบผสม": 6140,
	        "6143 = อนุบาล + ประถมศึกษา": 6143,
	        "6142 = อนุบาล + ประถมศึกษา+มัธยมศึกษา": 6142,
	        "6143 = ประถมศึกษา + มัธยมศึกษา": 6143,
	        "6150 = ระดับอาชีวศึกษา": 6150,
	        "6160 = ระดับอุดมศึกษา": 6160,
	        "6180 = สถาบันการศึกษาอื่น ๆ (วิทยาลัยสงฆ์ สารพัดช่าง ศูนย์การศึกษานอกระบบและการศึกษาตามอัธยาศัย)": 6180,
            "6200 = สถาบันศาสนา": 6200,
	        "6210 = วัด": 6210,
	        "6211 = วัดที่มีเตาเผาศพไฟฟ้า": 6211,
	        "6212 = วัดที่ไม่มีเตาเผาศพไฟฟ้า": 6212,
	        "6220 = สำนักสงฆ์": 6220,
	        "6230 = โบสถ์คริสต์": 6230,
	        "6240 = มัสยิด": 6240,
	        "6250 = ศาลเจ้า": 6250,
	        "6260 = ฌาปนสถาน": 6260,
	        "6270 = สุสาน": 6270,
	        "6280 = ศาสนสถานอื่น ๆ": 6280,
	        "6300 = สถาบันราชการ": 6300,
	        "6130 = ศาลาว่าการกรุงเทพมหานคร": 6130,
	        "6320 = สำนักงานเขต": 6320,
	        "6340 = สถานีตำรวจ และสถานที่ที่เกี่ยวข้อง กับราชการตำรวจ": 6340,
	        "6350 = สถานีดับเพลิง (สำนักป้องกันและบรรเทาสาธารณภัย)": 6350,
	        "6370 = ทัณฑสถาน": 6370,
	        "6380 = สถานที่ราชการอื่น ๆ": 6380,
	        "6381 = องค์กรอิสระของรัฐ": 6381,
	        "6382 = สถานทูต สถานกงสุล": 6382,
	        "6383 = หน่วยงานต่างประเทศ": 6383,
	        "6400 = รัฐวิสาหกิจ": 6400,
	        "6500 = การสาธาณสุข": 6500,
	        "6510 = สถานีอนามัยและศูนย์อนามัย": 6510,
	        "6511 = ศูนย์บริการสาธารณสุขและ ศูนย์บริการสาธารณสุขสาขา": 6511,
	        "6520 = คลีนิครัฐ": 6520,
	        "6530 = โรงพยาบาลรัฐ": 6530,
	        "6580 = การสาธาณสุขอื่น ๆ": 6580,
	        "6600 = ศิลปวัฒนธรรม": 6600,
	        "6610 = ศูนย์วัฒนธรรม": 6610,
            "6620 = พิพิธภัณฑ์ / หอจดหมายเหตุ": 6620,
            "6630 = ห้องสมุด": 6630,
            "6640 = หอศิลป์": 6640,
            "6650 = ศาลาประชาคม (ไม่ใช่อาคารประกอบของหน่วยงานราชการ)": 6650,
            "6800 = สาธารณูปการอื่น ๆ": 6800,
            "6830 = สถานสงเคราะห์ สมาคมฌาปนกิจสงเคราะห์ มูลนิธิเพื่อการศาสนา": 6830,
            "6831 = มูลนิธิอื่น ๆ ที่ไม่ใช่เพื่อการศาสนา": 6831,
            "7000 = นันทนาการ": 7000,
            "7200 = พื้นที่อนุรักษ์เพื่อศิลปะและวัฒธรรมไทย": 7200,
            "7210 = โบราณสถาน": 7210,
            "7220 = อนุสรณ์สถาน / อนุสาวรีย์": 7220,
            "7300 = นันทนาการ": 7300,
            "7310 = สวนสาธารณะ จุดบริการนักท่องเที่ยว": 7310,
            "7320 = การกีฬา": 7320,
            "7321 = สนามกีฬากลางแจ้งที่ไม่มีอัฒจันทร์": 7321,
            "7322 = สนามกีฬากลางแจ้งที่มีอัฒจันทร์": 7322,
            "7323 = สนามกีฬาในร่ม": 7323,
            "7324 = สนามกีฬากลางแจ้งและสนามกีฬาในร่ม": 7324,
            "7330 = สวนสัตว์": 7330,
            "7340 = สวนสนุก": 7340,
            "7380 = นันทนาการอื่น ๆ": 7380,
            "8000 = เกษตรกรรม": 8000,
            "8170 = เพิงพักเกษตร (เถียงนา ขนำ ห้างนา)": 8170,
            "8180 = เรือนเพาะชำ": 8180,
            "8190 = ยุ้งฉางขนาดใหญ่ ยุ้งฉางชุมชน": 8190,
            "8230 = อาคารอนุบาลสัตว์น้ำ": 8230,
            "8310 = คอกปศุสัตว์ บ้านนก": 8310,
            "8500 = การชลประทาน (ยกเว้นหน่วยงานราชการ)": 8500,
            "9000 = อาคารประเภทอื่น ๆ": 9900,
            "9991 = อาคารร้าง, อาคารที่ไม่ได้ใช้ประโยชน์": 9991,
	        "9992 = โรงจอดรถ อาคารที่จอดรถ": 9992,
	        "9993 = อาคารเชื่อมระหว่างอาคาร": 9993,
	        "9996 = ไม่ใช่อาคาร (Not building AREA)": 9996,
	        "9998 = อาคารกำลังก่อสร้าง": 9998,
            "9999 = ไม่สำรวจข้อมูล": 9999
        }
        self.bl_use_reverse_map = {v: k for k, v in self.bl_use_map.items()}

        self.bl_matl_map = {
            "1 = คอนกรีต": 1,
            "2 = ไม้ / ไม้เทียม": 2,
            "3 = คอนกรีตและไม้ หรือวัสดุอื่น": 3,
            "4 = เซลโลกรีต / ยิบซั่ม": 4,
            "5 = สังกะสี /เมทัลชีท": 5,
            "8 = อื่น ๆ": 8,
            "99 = ไม่ทราบประเภท": 99
        }
        self.bl_matl_reverse_map = {v: k for k, v in self.bl_matl_map.items()}

        self.initGui()

    def tr(self, message):
        return QCoreApplication.translate('Clickpointtoedit', message)

    def add_action(self, icon_path, text, callback, enabled_flag=True, add_to_menu=True,
                   add_to_toolbar=True, status_tip=None, whats_this=None, parent=None):
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)
        if status_tip:
            action.setStatusTip(status_tip)
        if whats_this:
            action.setWhatsThis(whats_this)
        if add_to_toolbar:
            self.iface.addToolBarIcon(action)
        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)
        self.actions.append(action)
        return action

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        if self.action:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu(self.menu, self.action)
        self.action = self.add_action(
            icon_path,
            text=self.tr(u'Turn on Edit เปิดโหมดแก้ไขข้อมูล'),
            callback=self.run,
            parent=self.iface.mainWindow()
        )
        self.first_start = True

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        self.actions = []
        if self.dock:
            self.iface.removeDockWidget(self.dock)
            self.dock = None
        if self.help_dock:
            self.iface.removeDockWidget(self.help_dock)
            self.help_dock = None

    def show_help_dock(self):
        if self.help_dock:
            self.iface.removeDockWidget(self.help_dock)
            self.help_dock = None

        self.help_dock = QDockWidget("วิธีใช้ Clickpointtoedit", self.iface.mainWindow())
        self.help_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        help_widget = QWidget()
        layout = QVBoxLayout()

        help_text = QLabel(
            "Hello Welcome have a good day \n"
            "\n"
            "English \n"
            "1. Please Select Vector Layer. \n"
            "2. Click Geometry type to edit. \n"
            "3. Edit data in field. \n"
            "5. Done Export Log Report to CSV file just put push Export button. \n"
            "Click Geometry type to hide. \n"
            "\n"
            "ภาษาไทย วิธีใช้งานปลั๊กอิน \n"
            "1.เลือกชั้นข้อมูลที่ต้องการแก้ไข \n"
            "2.คลิกเลือก Geometry ที่ต้องการแก้ไขข้อมูล \n"
            "3.กรอกข้อมูลในแถบแก้ไขที่ปรากฏทางขวา\n"
            "5.สามารถออกรายงานเป็น CSV แค่กดปุ่ม Export \n"
            "คลิกที่ Geometry type เพื่อซ่อนข้อความนี้ \n"
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        help_widget.setLayout(layout)
        self.help_dock.setWidget(help_widget)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.help_dock)
        self.help_dock.show()

    def hide_help_dock(self, feature=None):
        if self.help_dock:
            self.iface.removeDockWidget(self.help_dock)
            self.help_dock = None

    # ---------- helper: แถวคุม layout + ป้าย datatype + ปุ่มแก้ไขสำหรับ QLineEdit ----------
    def _make_text_row(self, line: QLineEdit, field_type_text: str) -> QWidget:
        line.setMinimumWidth(self.UI_MIN_WIDTH)
        line.setFixedHeight(self.UI_CTRL_HEIGHT)
        line.setEnabled(False)  # เริ่มปิดไว้ ต้องกด "แก้ไข" ก่อน
        line.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        edit_btn = QPushButton("Edit")
        edit_btn.setFixedHeight(self.UI_CTRL_HEIGHT)
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.setStyleSheet("QPushButton{padding:2px 8px;}")

        def toggle():
            if line.isEnabled():
                line.setEnabled(False)
                edit_btn.setText("Edit")
            else:
                line.setEnabled(True)
                line.setFocus()
                line.selectAll()
                edit_btn.setText("Lock")

        edit_btn.clicked.connect(toggle)

        type_label = QLabel(f"({field_type_text})")
        type_label.setMinimumWidth(self.TYPE_BADGE_MIN_W)
        type_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        type_label.setStyleSheet("color: gray; margin-left: 6px;")

        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        row_layout.addWidget(line, 1)
        row_layout.addWidget(edit_btn, 0)
        row_layout.addWidget(type_label, 0)

        row_widget = QWidget()
        row_widget.setLayout(row_layout)
        return row_widget

    # ---------- helper: แถวสำหรับคอนโทรลอื่น (เช่น ComboBox) + ป้าย datatype ----------
    def _make_row(self, control: QWidget, field_type_text: str) -> QWidget:
        control.setMinimumWidth(self.UI_MIN_WIDTH)
        control.setFixedHeight(self.UI_CTRL_HEIGHT)
        if isinstance(control, QComboBox):
            control.setSizeAdjustPolicy(QComboBox.AdjustToContentsOnFirstShow)
            control.setMinimumContentsLength(24)
        control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        type_label = QLabel(f"({field_type_text})")
        type_label.setMinimumWidth(self.TYPE_BADGE_MIN_W)
        type_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        type_label.setStyleSheet("color: gray; margin-left: 6px;")

        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        row_layout.addWidget(control, 1)
        row_layout.addWidget(type_label, 0)

        row_widget = QWidget()
        row_widget.setLayout(row_layout)
        return row_widget

    # ---------- helper: เคลียร์ทุก highlight แบบชัวร์ ----------
    def _clear_all_highlights(self):
        try:
            items = []
            if self.highlight:
                items.append(self.highlight)
                self.highlight = None
            items += self.saved_highlights
            self.saved_highlights = []

            for h in items:
                try:
                    if hasattr(h, "hide"):
                        h.hide()
                    if hasattr(h, "setVisible"):
                        h.setVisible(False)
                    if hasattr(h, "deleteLater"):
                        h.deleteLater()
                except Exception:
                    pass

            try:
                self.canvas.refresh()
            except Exception:
                pass
        except Exception:
            pass

    def run(self):
        layer = self.iface.activeLayer()
        if not isinstance(layer, QgsVectorLayer):
            self.iface.messageBar().pushWarning("No vector layer", "Please select a vector layer first.")
            return

        self.show_help_dock()

        self.tool = CustomIdentifyTool(self.canvas, layer)
        self.tool.feature_clicked.connect(self.onFeatureIdentified)
        self.tool.feature_clicked.connect(self.hide_help_dock)

        self.canvas.setMapTool(self.tool)

    def onFeatureIdentified(self, feature):
        manual_max_length = {
            "BLDG_ID": 15, "BL_TYPE": 2, "BL_NSTOREY": 2, "BL_NUNIT": 4, "BL_UNIT_F": 10,
            "BL_AREA_FLAG": 1, "BL_NAME_T": 100, "BL_NAME_E": 100, "BL_HOUSENUM": 10,
            "BL_VILLNUM": 10, "BL_VILLAGE": 35, "BL_ROAD": 150, "BL_SUBDISTRICT": 30,
            "BL_DISTRICT": 30, "BL_CHANGWAT": 30, "BL_POSTCODE": 5, "BL_ADDRESS": 180,
            "BL_ACT_MAJOR": 45, "BL_ACT_MINOR": 45, "BL_ACT_OTHER": 45, "REMARK": 255,
            "MATCHING": 1, "STATUS": 2, "SOURCE": 2, "S_DATE": 6, "CREATED_USER": 255,
            "LAST_EDITED_USER": 255, "BL_HID": 11, "BL_PAGE_NO": 50
        }

        layer = self.iface.activeLayer()
        if not isinstance(layer, QgsVectorLayer):
            return

        # ลบแดงเดิม สร้างแดงใหม่ (ไม่ยุ่งกับ green)
        if self.highlight:
            self.highlight.hide()
            self.highlight = None

        self.highlight = QgsHighlight(self.canvas, feature.geometry(), layer)
        self.highlight.setColor(Qt.red)
        self.highlight.setWidth(3)
        self.highlight.show()

        if not layer.isEditable():
            layer.startEditing()

        if self.dock:
            self.iface.removeDockWidget(self.dock)

        self.dock = QDockWidget("Edit Feature", self.iface.mainWindow())
        self.dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.dock.setMinimumWidth(self.UI_DOCK_MIN_W)
        self.dock.setMaximumWidth(self.UI_DOCK_MAX_W)
        self.dock.resize(self.UI_DOCK_PREF_W, self.UI_DOCK_PREF_H)

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self.fields = []
        form_widget = QWidget()
        form_widget.setLayout(form)

        for field in layer.fields():
            field_type = field.typeName().lower()
            # ข้าม field geometry, blob, clob ไม่ต้องโชว์/ไม่ต้องแก้
            if field_type in ["geometry", "blob", "clob"]:
                continue

            value = feature[field.name()]
            if value is None:
                value = ""

            # === BL_OWNER (ComboBox → ไม่มีปุ่มแก้ไข) ===
            if field.name() == "BL_OWNER":
                combo = NoScrollComboBox()
                combo.addItems(list(self.bl_owner_map.keys()))
                combo.setEditable(False)
                if value:
                    try:
                        show_value = self.bl_owner_reverse_map.get(int(value), "")
                        if show_value:
                            combo.setCurrentText(show_value)
                    except Exception:
                        pass
                form.addRow(field.name(), self._make_row(combo, field_type))
                self.fields.append((field.name(), combo))
                continue

            # === BL_AREA_FLAG ===
            if field.name() == "BL_AREA_FLAG":
                combo = NoScrollComboBox()
                combo.addItems(list(self.bl_area_flag_map.keys()))
                combo.setEditable(False)
                if value:
                    show_value = self.bl_area_flag_reverse_map.get(str(value), "")
                    if show_value:
                        combo.setCurrentText(show_value)
                form.addRow(field.name(), self._make_row(combo, field_type))
                self.fields.append((field.name(), combo))
                continue

            # === BL_TYPE ===
            if field.name() == "BL_TYPE":
                combo = NoScrollComboBox()
                combo.addItems(list(self.bl_type_map.keys()))
                combo.setEditable(False)
                if value:
                    try:
                        show_value = self.bl_type_reverse_map.get(int(value), "")
                        if show_value:
                            combo.setCurrentText(show_value)
                    except Exception:
                        pass
                form.addRow(field.name(), self._make_row(combo, field_type))
                self.fields.append((field.name(), combo))
                continue

            # === BL_MATL ===
            if field.name().strip().upper() == "BL_MATL":
                combo = NoScrollComboBox()
                combo.addItems(list(self.bl_matl_map.keys()))
                combo.setEditable(False)
                combo.setMaxVisibleItems(12)
                if value not in [None, "", "NULL"]:
                    try:
                        show_value = self.bl_matl_reverse_map.get(int(value), "")
                    except Exception:
                        show_value = value if isinstance(value, str) and value in self.bl_matl_map else ""
                    if show_value:
                        combo.setCurrentText(show_value)
                form.addRow(field.name(), self._make_row(combo, field_type))
                self.fields.append((field.name(), combo))
                continue

            # === BL_USE (textbox disabled + ปุ่มค้นหา + ปุ่มแก้ไข) ===
            if field.name().strip().upper() == "BL_USE":
                bl_use_edit = QLineEdit()
                current_key = ""
                if value not in [None, "", "NULL"]:
                    try:
                        current_key = self.bl_use_reverse_map.get(int(value), "")
                    except Exception:
                        current_key = ""
                if current_key:
                    bl_use_edit.setText(current_key)

                # แถวหลัก: TextBox + ปุ่มแก้ไข + ป้าย datatype
                form.addRow(field.name(), self._make_text_row(bl_use_edit, field_type))
                self.fields.append((field.name(), bl_use_edit))

                # แถวค้นหา/เปลี่ยน (เปิด dialog รายการทั้งหมด)
                search_wrap = QWidget()
                sr = QHBoxLayout()
                sr.setContentsMargins(0, 0, 0, 0)
                search_edit = QLineEdit()
                search_edit.setPlaceholderText("พิมพ์แล้วกด Enter หรือคลิก ‘ค้นหา/เปลี่ยน’ เพื่อเปิดรายการทั้งหมด")
                search_btn = QPushButton("ค้นหา/เปลี่ยน")
                search_edit.setMinimumWidth(self.UI_MIN_WIDTH)
                search_edit.setFixedHeight(self.UI_CTRL_HEIGHT)
                search_btn.setFixedHeight(self.UI_CTRL_HEIGHT)
                sr.addWidget(search_edit, 1)
                sr.addWidget(search_btn, 0)
                search_wrap.setLayout(sr)

                def show_all_picker(prefill_text: str):
                    current_key_now = bl_use_edit.text().strip()

                    dlg = QDialog(self.iface.mainWindow())
                    dlg.setWindowTitle("เลือกรายการ BL_USE ทั้งหมด")
                    dlg.resize(360, 360)  # Small
                    v = QVBoxLayout(dlg)
                    tip = QLabel("พิมพ์เพื่อกรองรายการ แล้วดับเบิลคลิกเพื่อเลือก (มีการยืนยันก่อนตั้งค่า)")
                    v.addWidget(tip)
                    filter_edit = QLineEdit(dlg)
                    filter_edit.setPlaceholderText("กรุณาใส่ code เช่น 2280 หรือชื่อที่ต้องค้นหา")
                    v.addWidget(filter_edit)

                    listw = QListWidget(dlg)
                    for lbl, code in sorted(self.bl_use_map.items(), key=lambda x: x[1]):
                        it = QListWidgetItem(lbl, listw)
                        it.setData(Qt.UserRole, lbl)
                    v.addWidget(listw)

                    def apply_filter(txt: str):
                        t = (txt or "").strip()
                        for i in range(listw.count()):
                            it = listw.item(i)
                            it.setHidden(False if not t else (t not in it.text()))
                        # default selection
                        if current_key_now:
                            items = listw.findItems(current_key_now, Qt.MatchExactly)
                            if items and not items[0].isHidden():
                                listw.setCurrentItem(items[0])
                                listw.scrollToItem(items[0])
                                return
                        for i in range(listw.count()):
                            it = listw.item(i)
                            if not it.isHidden():
                                listw.setCurrentRow(i)
                                listw.scrollToItem(it)
                                break

                    def on_pick(it: QListWidgetItem):
                        key_lbl = it.data(Qt.UserRole)
                        rep = QMessageBox.question(
                            self.iface.mainWindow(),
                            "ยืนยันการเลือก",
                            f"ตั้งค่า BL_USE เป็น:\n{key_lbl}\nตกลงหรือไม่?",
                            QMessageBox.Yes | QMessageBox.No
                        )
                        if rep == QMessageBox.Yes:
                            bl_use_edit.setText(key_lbl)
                            dlg.accept()

                    listw.itemDoubleClicked.connect(on_pick)
                    filter_edit.textChanged.connect(apply_filter)

                    if prefill_text:
                        filter_edit.setText(prefill_text)
                    apply_filter(filter_edit.text())

                    dlg.exec_()

                search_btn.clicked.connect(lambda: show_all_picker(search_edit.text()))
                search_edit.returnPressed.connect(lambda: show_all_picker(search_edit.text()))
                form.addRow("ค้นหา/เปลี่ยน BL_USE", search_wrap)
                continue

            # --- ฟิลด์อื่นๆ: QLineEdit + ปุ่มแก้ไข ---
            line_edit = QLineEdit(str(value))
            if field.name() in manual_max_length:
                line_edit.setMaxLength(manual_max_length[field.name()])
            if field_type in ["int", "integer", "integer32", "integer64"]:
                line_edit.setToolTip("กรอกตัวเลขจำนวนเต็ม เช่น 1,2,3")
            elif field_type in ["double", "real", "float"]:
                line_edit.setToolTip("กรอกตัวเลขทศนิยม เช่น 1.1, 1.110")
            elif field_type in ["date", "datetime"]:
                line_edit.setToolTip("กรอกวันที่ในรูปแบบ YYYY-MM-DD")
            else:
                line_edit.setToolTip("กรอกข้อความ เช่น ถนนสุขุมวิท")

            form.addRow(field.name(), self._make_text_row(line_edit, field_type))
            self.fields.append((field.name(), line_edit))

        scroll_area.setWidget(form_widget)
        layout.addWidget(scroll_area)

        save_btn = QPushButton("Save") 
        save_btn.setStyleSheet("background-color: green; color: white;")
        save_btn.setFixedHeight(self.UI_CTRL_HEIGHT)
        save_btn.clicked.connect(lambda: self.confirm_save(layer, feature.id(), feature))
        layout.addWidget(save_btn)

        export_btn = QPushButton("Export Log Report Edit")
        export_btn.setFixedHeight(self.UI_CTRL_HEIGHT)
        export_btn.clicked.connect(self.export_layer_and_log)
        layout.addWidget(export_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("background-color: red; color: white;")
        cancel_btn.setFixedHeight(self.UI_CTRL_HEIGHT)
        cancel_btn.clicked.connect(self.cancel_action)
        layout.addWidget(cancel_btn)

        container = QWidget()
        container.setLayout(layout)
        container.setMinimumWidth(self.UI_DOCK_MIN_W - 40)
        container.setStyleSheet("""
            QLineEdit, QComboBox { padding: 4px; }
            QPushButton { padding: 4px 10px; }
        """)
        self.dock.setWidget(container)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.dock.resize(self.UI_DOCK_PREF_W, self.UI_DOCK_PREF_H)
        self.dock.show()

    def save_data(self, layer, feature_id, feature):
        if not layer.isEditable():
            return

        fields = layer.fields()
        updated = False

        manual_max_length = {
            "BLDG_ID": 15, "BL_TYPE": 2, "BL_NSTOREY": 2, "BL_NUNIT": 4, "BL_UNIT_F": 10,
            "BL_AREA_FLAG": 1, "BL_NAME_T": 100, "BL_NAME_E": 100, "BL_HOUSENUM": 10,
            "BL_VILLNUM": 10, "BL_VILLAGE": 35, "BL_ROAD": 150, "BL_SUBDISTRICT": 30,
            "BL_DISTRICT": 30, "BL_CHANGWAT": 30, "BL_POSTCODE": 5, "BL_ADDRESS": 180,
            "BL_ACT_MAJOR": 45, "BL_ACT_MINOR": 45, "BL_ACT_OTHER": 45, "REMARK": 255,
            "MATCHING": 1, "STATUS": 2, "SOURCE": 2, "S_DATE": 6, "CREATED_USER": 255,
            "LAST_EDITED_USER": 255, "BL_HID": 11, "BL_PAGE_NO": 50
        }

        for name, widget in self.fields:
            idx = fields.indexFromName(name)
            field = fields[idx]
            field_type = field.typeName().lower()

            if field_type in ["geometry", "blob", "clob"]:
                continue

            # === ComboBox ===
            if name == "BL_OWNER" and isinstance(widget, QComboBox):
                text = widget.currentText()
                value = self.bl_owner_map.get(text)
                old_value = feature[name]

            elif name == "BL_AREA_FLAG" and isinstance(widget, QComboBox):
                text = widget.currentText()
                value = self.bl_area_flag_map.get(text)
                old_value = feature[name]

            elif name == "BL_TYPE" and isinstance(widget, QComboBox):
                text = widget.currentText()
                value = self.bl_type_map.get(text)
                old_value = feature[name]

            elif name.strip().upper() == "BL_MATL" and isinstance(widget, QComboBox):
                text = widget.currentText()
                value = self.bl_matl_map.get(text)
                old_value = feature[name]

            # === BL_USE จาก QLineEdit (อนุญาตพิมพ์/ค้นหา) ===
            elif name.strip().upper() == "BL_USE" and isinstance(widget, QLineEdit):
                t = widget.text().strip()
                if t in self.bl_use_map:
                    value = self.bl_use_map[t]
                elif t.isdigit():
                    code = int(t)
                    value = code if code in self.bl_use_reverse_map else None
                else:
                    value = None
                old_value = feature[name]

            # === อื่น ๆ QLineEdit ===
            else:
                value_str = widget.text().strip()
                old_value = feature[name]

                if value_str.upper() in ["NULL", "NONE", ""]:
                    value = None
                elif field_type in ['integer', 'int', 'integer32', 'integer64']:
                    try:
                        value = int(value_str)
                    except Exception:
                        value = None
                elif field_type in ['double', 'real', 'float']:
                    try:
                        value = float(value_str)
                    except Exception:
                        value = None
                elif name in manual_max_length:
                    safe_str = str(value_str)
                    max_len = manual_max_length[name]
                    value = safe_str[:max_len] if len(safe_str) > max_len else safe_str
                elif field_type in ['string', 'varchar', 'varchar2', 'nvarchar2', 'text']:
                    value = str(value_str)
                elif field_type in ['date', 'datetime']:
                    value = value_str
                else:
                    value = value_str

            equal_none = (value is None and old_value in [None, '', 'NULL', 'None'])
            if (value != old_value) and not equal_none:
                layer.changeAttributeValue(feature_id, idx, value)
                updated = True

        if updated:
            layer.commitChanges()

            # เพิ่ม highlight สีเขียวและเก็บไว้ (เคลียร์ตอน Export เท่านั้น)
            green_highlight = QgsHighlight(self.canvas, feature.geometry(), layer)
            green_highlight.setColor(Qt.green)
            green_highlight.setWidth(3)
            green_highlight.show()
            self.saved_highlights.append(green_highlight)

            # log การแก้ไข
            log_path = os.path.join(os.path.expanduser("~"), "edit_log.csv")
            with open(log_path, "a", newline="", encoding="utf-8") as logfile:
                writer = csv.writer(logfile)
                writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), layer.name(), feature_id])

            # แจ้งผล และปิดหน้าจอปลั๊กอิน (ไม่ยุ่งกับ highlight)
            QMessageBox.information(
                self.iface.mainWindow(),
                "Ok บันทึกสำเร็จ",
                "Data have saved ข้อมูลถูกบันทึกเรียบร้อยแล้ว"
            )

            try:
                if self.dock:
                    self.iface.removeDockWidget(self.dock)
                    self.dock.close()
                    self.dock = None
                if self.help_dock:
                    self.iface.removeDockWidget(self.help_dock)
                    self.help_dock.close()
                    self.help_dock = None
            except Exception:
                pass

        else:
            QMessageBox.information(
                self.iface.mainWindow(),
                "ไม่มีการเปลี่ยนแปลง",
                "ไม่มีข้อมูลที่ถูกเปลี่ยนแปลง ไม่มีการบันทึกข้อมูลใหม่"
            )

    def confirm_save(self, layer, feature_id, feature):
        reply = QMessageBox.question(
            self.iface.mainWindow(),
            "Confirm ? ยืนยันการบันทึก",
            "Do you Confirm to save ? คุณแน่ใจหรือไม่ว่าต้องการบันทึกการแก้ไขนี้?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.save_data(layer, feature_id, feature)

    def cancel_action(self):
        reply = QMessageBox.question(
            self.iface.mainWindow(),
            "Cancle ? ยกเลิกการแก้ไข",
            "Do you Confirm to cancle ? คุณแน่ใจหรือไม่ว่าต้องการยกเลิกการแก้ไข?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            layer = self.iface.activeLayer()
            layer.rollBack()
            QMessageBox.information(self.iface.mainWindow(), "Cancled ยกเลิกแล้ว",
                                    "Edit to cancle การแก้ไขถูกยกเลิกเรียบร้อยแล้ว")
            if self.dock:
                self.iface.removeDockWidget(self.dock)
                self.dock.close()
                self.dock = None

    def export_layer_and_log(self):
        reply = QMessageBox.question(
            self.iface.mainWindow(),
            "Export Log",
            "Do you want to export edit log now? คุณต้องการ export รายงานการแก้ไขหรือไม่?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        log_path = os.path.join(os.path.expanduser("~"), "edit_log.csv")
        edited_data = {}

        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8") as logfile:
                    for line in logfile:
                        parts = line.strip().split(",")
                        if len(parts) >= 3:
                            try:
                                fid = int(parts[2])
                                timestamp = parts[0]
                                edited_data[fid] = timestamp
                            except ValueError:
                                continue
            except Exception as e:
                print("Error reading log:", e)

        layer = self.iface.activeLayer()
        if not layer:
            QMessageBox.warning(self.iface.mainWindow(), "No Feature layer ไม่มีชั้นข้อมูล",
                                "Please select layers before Export please. กรุณาเลือกชั้นข้อมูลก่อน export")
            return

        csv_path, _ = QFileDialog.getSaveFileName(None, "Save CSV File", "", "CSV Files (*.csv)")
        if not csv_path:
            return

        try:
            with codecs.open(csv_path, "w", "utf-8-sig") as file:
                writer = csv.writer(file)
                headers = [field.name() for field in layer.fields()] + ["edited_at"]
                writer.writerow(headers)

                for feature in layer.getFeatures():
                    if feature.id() in edited_data:
                        values = [feature[field.name()] for field in layer.fields()]
                        values.append(edited_data[feature.id()])
                        writer.writerow(values)

            QMessageBox.information(self.iface.mainWindow(), "Export Log", "Export log เรียบร้อยแล้ว")

            # ล้างทุก highlight หลัง export (ซ่อน + deleteLater + refresh)
            self._clear_all_highlights()

            if os.path.exists(log_path):
                os.remove(log_path)

        except Exception as e:
            QMessageBox.warning(self.iface.mainWindow(), "Error เกิดข้อผิดพลาด",
                                f"Can't export to CSV. ไม่สามารถ export CSV ได้:\n{str(e)}")
