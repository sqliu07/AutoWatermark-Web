from flask import Blueprint, Response, current_app, jsonify, redirect, render_template, request, send_file, stream_with_context

from constants import AppConstants
from extensions import limiter
from routes._utils import is_browser_request
from services import task_lifecycle, upload_workflow


bp = Blueprint("upload", __name__)


@bp.route("/upload", methods=["GET"])
def upload_entry_redirect():
    return redirect("/")


@bp.route("/upload", methods=["POST"])
@limiter.limit(AppConstants.UPLOAD_RATE_LIMIT)
def upload_file():
    state = current_app.extensions["state"]
    style_config = current_app.extensions.get("watermark_styles", {})
    result = upload_workflow.handle_upload(
        files=request.files,
        form=request.form,
        args=request.args,
        config=current_app.config,
        state=state,
        style_config=style_config,
        logger=current_app.logger,
    )
    return jsonify(result.payload), result.status_code


@bp.route("/upload/confirm_logo", methods=["POST"])
@limiter.limit(AppConstants.UPLOAD_RATE_LIMIT)
def confirm_logo_choice():
    state = current_app.extensions["state"]
    style_config = current_app.extensions.get("watermark_styles", {})
    payload = request.get_json(silent=True) or {}
    result = upload_workflow.confirm_logo_choice(
        payload=payload,
        state=state,
        upload_folder=current_app.config["UPLOAD_FOLDER"],
        style_config=style_config,
        logger=current_app.logger,
    )
    return jsonify(result.payload), result.status_code


@bp.route("/upload/confirm_logo", methods=["GET"])
def confirm_logo_entry_redirect():
    return redirect("/")


@bp.route("/upload/confirm_options", methods=["POST"])
@limiter.limit(AppConstants.UPLOAD_RATE_LIMIT)
def confirm_options():
    """确认 HDR/Motion Photo 选项后继续处理。"""
    state = current_app.extensions["state"]
    style_config = current_app.extensions.get("watermark_styles", {})
    payload = request.get_json(silent=True) or {}
    result = upload_workflow.confirm_options(
        payload=payload,
        state=state,
        upload_folder=current_app.config["UPLOAD_FOLDER"],
        style_config=style_config,
        logger=current_app.logger,
    )
    return jsonify(result.payload), result.status_code


@bp.route("/tasks/<task_id>/retry", methods=["POST"])
@limiter.limit(AppConstants.UPLOAD_RATE_LIMIT)
def retry_task(task_id):
    state = current_app.extensions["state"]
    style_config = current_app.extensions.get("watermark_styles", {})
    result = task_lifecycle.retry_failed_task(
        task_id=task_id,
        state=state,
        upload_folder=current_app.config["UPLOAD_FOLDER"],
        style_config=style_config,
        logger=current_app.logger,
    )
    return jsonify(result.payload), result.status_code


@bp.route("/status/<task_id>", methods=["GET"])
def get_task_status(task_id):
    if is_browser_request():
        return redirect("/")

    state = current_app.extensions["state"]
    task = state.get_task(task_id)
    if not task:
        return jsonify({"status": "unknown"}), 404
    return jsonify(
        {
            "status": task.get("status"),
            "progress": task.get("progress", 0.0),
            "stage": task.get("stage"),
            "result": task.get("result"),
            "error": task.get("error"),
        }
    )


@bp.route("/upload/<filename>")
def upload_file_served(filename):
    """预览端点：inline 展示，不触发焚烧。"""
    result = upload_workflow.get_preview_file(
        filename=filename,
        args=request.args,
        upload_folder=current_app.config["UPLOAD_FOLDER"],
        is_browser=is_browser_request(),
    )
    if result.render_deleted:
        return render_template("image_deleted.html"), result.status_code
    if result.error:
        return jsonify(error=result.error), result.status_code
    return send_file(result.file_path)


@bp.route("/upload/<filename>/video")
@limiter.limit(AppConstants.UPLOAD_RATE_LIMIT)
def upload_motion_video(filename):
    """从 Motion Photo 文件中提取视频部分，返回 video/mp4。"""
    result = upload_workflow.get_motion_video(
        filename=filename,
        args=request.args,
        upload_folder=current_app.config["UPLOAD_FOLDER"],
        logger=current_app.logger,
    )
    if result.error:
        return jsonify(error=result.error), result.status_code

    def generate_video_stream():
        with open(result.file_path, "rb") as fp:
            fp.seek(result.video_start)
            while True:
                chunk = fp.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

    response = Response(stream_with_context(generate_video_stream()), mimetype="video/mp4")
    response.headers["Content-Length"] = str(result.file_size - result.video_start)
    response.headers["Content-Disposition"] = f'inline; filename="{result.filename}.mp4"'
    return response
