# A wrapper around WireViz for bringing it to the web. Easily document cables and wiring harnesses.
#
# Copyright (C) 2020  Jürgen Key <jkey@arcor.de>
# Copyright (C) 2021  Andreas Motl <andreas.motl@panodata.org>
#
# This program is licensed under the GNU Affero General Public License v3.0.
# See <http://www.gnu.org/licenses/>.

from pathlib import Path, PurePath
import os
import subprocess
import tempfile
import werkzeug
from flask import Blueprint, Response, request
from flask_restx import Api, Resource, reqparse

from wireviz_web import __version__
from wireviz_web.core import (
    decode_plantuml,
    mimetype_to_type,
    type_to_mimetype,
    wireviz_render,
)

# ──────────────────────────────
# Request parser pour l’upload YAML
file_upload = reqparse.RequestParser()
file_upload.add_argument(
    "yml_file",
    type=werkzeug.datastructures.FileStorage,
    location="files",
    required=True,
    help="YAML file",
)

wireviz_blueprint = Blueprint("wireviz-web", __name__)
api = Api(
    app=wireviz_blueprint,
    version=__version__,
    title="WireViz-Web",
    description="A wrapper around WireViz to render cable diagrams on the web.",
    doc="/doc",
    catch_all_404s=True,
)

ns = api.namespace("", description="WireViz-Web REST API")

# ──────────────────────────────
@ns.route("/render")
class RenderRegular(Resource):
    @api.expect(file_upload)
    @ns.produces(["image/png", "image/svg+xml"])
    def post(self) -> Response:
        """
        Upload a WireViz YAML (field **yml_file**) and optional images (field **images**).
        The HTTP *Accept* header chooses SVG (default) or PNG.
        """
        # ────────────── paramètres et fichiers
        mimetype = request.headers.get("accept") or "image/svg+xml"
        args = file_upload.parse_args()
        yaml_input = args["yml_file"].read()
        images = request.files.getlist("images")

        # ────────────── noms de fichiers
        input_filename = args["yml_file"].filename            # ex. demo01.yaml
        fmt = mimetype_to_type(mimetype)                      # svg | png
        output_filename = PurePath(input_filename).with_suffix(f".{fmt}").name

        # ────────────── travail en répertoire temporaire
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "input.yml")
            with open(src, "wb") as f:
                f.write(yaml_input)

            # copier les images dans tmp/resources/
            if images:
                resdir = os.path.join(tmp, "resources")
                os.makedirs(resdir, exist_ok=True)
                for img in images:
                    img.save(os.path.join(resdir, img.filename))  # conserver le nom original

            # ───────── WireViz : dossier de sortie = tmp
            try:
                cmd = ["wireviz", src, "-o", tmp]
                if fmt != "svg":                       # svg est le défaut
                    cmd.extend(["-f", fmt])
                subprocess.check_call(cmd)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"WireViz failed: {e}") from e

            # fichier généré = input.<fmt>
            out_file = os.path.join(tmp, f"{Path(src).stem}.{fmt}")
            with open(out_file, "rb") as f:
                payload = f.read()

        return Response(
            payload,
            mimetype=mimetype,
            headers={"Content-Disposition": f"attachment; filename={output_filename}"},
        )

# ──────────────────────────────
@ns.route("/plantuml/<imagetype>/<encoded>")
@ns.param("encoded", "PlantUML Text Encoding format")
class RenderPlantUML(Resource):
    @ns.produces(["image/png", "image/svg+xml"])
    def get(self, imagetype: str, encoded: str) -> Response:
        """Render a PlantUML diagram via WireViz-Web."""
        mimetype = type_to_mimetype(imagetype)
        yaml_input = decode_plantuml(input_plantuml=encoded)
        return wireviz_render(
            input_yaml=yaml_input,
            output_mimetype=mimetype,
            output_filename=f"rendered.{imagetype}",
        )
