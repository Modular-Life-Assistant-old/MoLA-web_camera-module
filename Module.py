import os
import time
from flask import abort, Blueprint, redirect, render_template, Response, \
    send_file, url_for
from io import BytesIO

from core import ModuleManager
from helpers.modules.BaseModule import BaseModule


class Module(BaseModule):
    cache_delay = 10
    __cache_camera_list = {}
    __cache_time = 0

    def get_camera_list(self):
        """Get cameras devices"""
        # get cache
        current_time = time.time()
        if self.cache_delay > current_time - self.__cache_time:
            return self.__cache_camera_list

        camera_list = {}

        for module_name in ModuleManager.get_active_modules():
            devices = getattr(ModuleManager.get(module_name), 'devices', {})

            for device in devices.values():
                name = device.name
                num = 0

                # duplicate ?
                while name in camera_list:
                    num += 1
                    name = '%s%d' % (device.name, num)

                camera_list[device.name] = device

        self.__cache_camera_list = camera_list
        self.__cache_time = current_time
        return camera_list

    def started(self):
        """Register mapping url to web server"""
        template_folder = os.path.join(self.module_path, 'templates')
        app = Blueprint('Camera', __name__, url_prefix='/camera',
                        template_folder=template_folder)
        app.add_url_rule('/', 'home', view_func=self._index)
        app.add_url_rule('/cmd/<camera_name>/<cmd>', 'cmd', view_func=self._cmd)
        app.add_url_rule('/img/<camera_name>', 'img', view_func=self._img)
        app.add_url_rule('/list', 'list', view_func=self._list)
        app.add_url_rule('/thumbnail/<camera_name>', 'thumbnail', view_func=self._thumbnail)
        app.add_url_rule('/view/<camera_name>', 'view', view_func=self._view)
        self.call('web', 'add_blueprint', app)

    def _cmd(self, camera_name, cmd):
        """Camera image"""
        camera = self.get_camera_list().get(camera_name)

        if not camera:
            return

        if cmd not in ('move_top', 'move_left', 'move_right', 'move_bottom',
                       'move_stop', 'zoom_in', 'zoom_out'):
            return

        handler = getattr(camera, cmd, None)
        if not handler:
            return

        handler()
        return 'ok'

    def _img(self, camera_name, size=()):
        """Camera image"""
        camera = self.get_camera_list().get(camera_name)

        if not camera:
            return render_template('message.html', message='Camera not found')

        img = camera.get_snapshot()
        if not img:
            return abort(404)

        # is not streaming ?
        if size or not camera.has_streaming():
            # resize
            if size:
                img.thumbnail(size)

            # img to file pointer
            img_fp = BytesIO()
            img.save(img_fp, 'JPEG', quality=70)
            img_fp.seek(0)
            return send_file(img_fp, mimetype='image/jpeg')

        # streaming
        return Response(self.__streaming(camera),
                        mimetype='multipart/x-mixed-replace; boundary=frame')

    def _index(self):
        """Index page"""
        camera_list = self.get_camera_list()

        if not camera_list:
            return render_template('message.html', message='No camera found')

        if len(camera_list) :#> 1:
            return redirect(url_for('.list'))

        return redirect(url_for('.view', camera_name=list(camera_list)[0]))

    def _list(self):
        """Camera list page"""
        return render_template('list.html', cameras=self.get_camera_list())

    def _thumbnail(self, camera_name):
        """Camera thumbnail image"""
        return self._img(camera_name, (400, 400))

    def _view(self, camera_name):
        """Camera view page"""
        camera = self.get_camera_list().get(camera_name)

        if not camera:
            return render_template('message.html', message='Camera not found')

        return render_template('camera.html', name=camera_name, camera=camera)

    def __streaming(self, camera):
        while True:
            frame = camera.get_streaming()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
