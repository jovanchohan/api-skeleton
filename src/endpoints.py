from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from http import HTTPStatus
from src.extensions import db
from src.models import Appointment, Doctor, DummyModel, WorkingHours
from webargs import fields, validate
from webargs.flaskparser import use_args
from datetime import date, time
from werkzeug.exceptions import BadRequest
from sqlalchemy.orm.exc import NoResultFound



home = Blueprint("/", __name__)


# Helpful documentation:
# https://webargs.readthedocs.io/en/latest/framework_support.html
# https://flask.palletsprojects.com/en/2.0.x/quickstart/#variable-rules


@home.route("/")
def index():
    return {"data": "OK"}


@home.route("/dummy_model/id/<id_>", methods=["GET"])
def dummy_model(id_):
    record = DummyModel.query.filter_by(id=id_).first()
    if record is not None:
        return record.json()
    else:
        return jsonify(None), HTTPStatus.NOT_FOUND


@home.route("/dummy_model", methods=["POST"])
@use_args({"value": fields.String()})
def dummy_model_create(args):
    new_record = DummyModel(value=args.get("value"))
    db.session.add(new_record)
    db.session.commit()
    return new_record.json()


@home.route("/doctor", methods=["POST"])
@use_args({"name": fields.String()})
def doctor_create(args):
    new_record = Doctor(name=args.get("name"))
    db.session.add(new_record)
    db.session.commit()
    return new_record.json()


@home.route("/working_hours", methods=["POST"])
@use_args(
    {
        "doctor_id": fields.String(),
        "day_of_week": fields.String(),
        "start_time": fields.String(),
        "end_time": fields.String(),
    }
)
def working_hours_create(args):
    doctor = Doctor.query.get(args["doctor_id"])
    if not doctor:
        return {"message": "Doctor not found"}, 404
    
    try:
        start_time = time.fromisoformat(args["start_time"])
        end_time = time.fromisoformat(args["end_time"])
    except ValueError:
        raise BadRequest("Invalid time format. Use HH:MM:SS format for start_time and end_time.")

    try:
        existing_record = WorkingHours.query.filter_by(doctor_id=args["doctor_id"], day_of_week=args["day_of_week"]).one()
        existing_record.start_time = start_time
        existing_record.end_time = end_time
        working_hours = existing_record
        db.session.commit()  
    except NoResultFound:
        working_hours = WorkingHours(
            doctor_id=args["doctor_id"],
            day_of_week=args["day_of_week"],
            start_time=start_time,
            end_time=end_time
        )
        db.session.add(working_hours)
        db.session.commit()

    return working_hours.json()

@home.route("/appointment", methods=["POST"])
@use_args(
    {
        "doctor_id": fields.String(required=True),
        "patient_name": fields.String(required=True),
        "appointment_date": fields.String(required=True),  # Date in ISO format (YYYY-MM-DD)
        "start_time": fields.String(required=True),  # Time in HH:MM:SS format
        "end_time": fields.String(required=True),  # Time in HH:MM:SS format
    }
)
def create_appointment(args):
    doctor = Doctor.query.get(args["doctor_id"])
    if not doctor:
        return {"message": "Doctor not found"}, HTTPStatus.NOT_FOUND
    
    try:
        appointment_date = date.fromisoformat(args["appointment_date"])
        start_time = time.fromisoformat(args["start_time"])
        end_time = time.fromisoformat(args["end_time"])
    except (ValueError, TypeError):
        return {"message": "Invalid date or time format"}, HTTPStatus.BAD_REQUEST
    
    working_hours = WorkingHours.query.filter_by(doctor_id=args["doctor_id"], day_of_week=appointment_date.strftime("%A").upper()).first()
    if not working_hours or start_time < working_hours.start_time or end_time > working_hours.end_time:
        return {"message": "Appointment is outside of the doctor's working hours"}, HTTPStatus.BAD_REQUEST

    overlapping_appointment = Appointment.query.filter_by(doctor_id=args["doctor_id"], appointment_date=appointment_date).filter(
        (Appointment.start_time < end_time) & (Appointment.end_time > start_time)
    ).first()

    if overlapping_appointment:
        return {"message": "Doctor already has an appointment at that time"}, HTTPStatus.BAD_REQUEST

    appointment = Appointment(
        doctor_id=args["doctor_id"],
        patient_name=args["patient_name"],
        appointment_date=appointment_date,
        start_time=start_time,
        end_time=end_time,
    )

    db.session.add(appointment)
    db.session.commit()

    return appointment.json()

@home.route("/appointments", methods=["GET"])
def get_appointments_by_time():
    doctor_id = request.args.get('doctor_id')
    start = request.args.get('start')
    end = request.args.get('end')

    try:
        start_datetime = datetime.strptime(start, "%Y-%m-%dT%H:%M:%S")
        end_datetime = datetime.strptime(end, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return {"message": "Invalid date or time format"}, HTTPStatus.BAD_REQUEST

    print("start", start_datetime)
    print("end", end_datetime)
    print("doctor", doctor_id)

    doctor = Doctor.query.get(doctor_id)
    if not doctor:
        return {"message": "Doctor not found"}, HTTPStatus.NOT_FOUND

    appointments = Appointment.query.filter_by(doctor_id=doctor_id).filter(
        (Appointment.appointment_date >= start_datetime.date()) &
        (Appointment.appointment_date <= end_datetime.date()) &
        (Appointment.start_time >= start_datetime.time()) &
        (Appointment.end_time <= end_datetime.time())
    ).all()

    if appointments:
        return jsonify([appointment.json() for appointment in appointments])
    else:
        return jsonify(None), HTTPStatus.NOT_FOUND

@home.route("/first_available_appointment", methods=["GET"])
def get_first_available_appointment():
    doctor_id = request.args.get('doctor_id')
    start = request.args.get('start')

    # Convert string timestamp to datetime object
    try:
        start_datetime = datetime.strptime(start, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return {"message": "Invalid date or time format"}, HTTPStatus.BAD_REQUEST

    doctor = Doctor.query.get(doctor_id)
    if not doctor:
        return {"message": "Doctor not found"}, HTTPStatus.NOT_FOUND

    # Query for appointments after the specified start date time
    appointments = Appointment.query.filter_by(doctor_id=doctor_id).filter(
        (Appointment.appointment_date >= start_datetime.date()) &
        (Appointment.start_time >= start_datetime.time())
    ).order_by(Appointment.start_time.asc()).all()

    if not appointments:
        # If there are no appointments, return the provided start time
        return {"first_available": start_datetime.strftime("%Y-%m-%dT%H:%M:%S")}

    
    # Check if first appointment overlaps with the start time
    if appointments[0].start_time >= start_datetime.time() and appointments[0].end_time <= start_datetime.time():
        # Overlapping, return the end time of the appointment
        return {"first_available": appointments[0].appointment_date + appointments[0].end_time.strftime("%Y-%m-%dT%H:%M:%S")}

    # Find the first gap in time between appointments
    for i in range(len(appointments) - 1):
        if appointments[i].end_time != appointments[i + 1].start_time:
            # A gap is found, return the end time of the first appointment with a gap
            return {"first_available": (appointments[i].appointment_date + appointments[-1].end_time).strftime("%Y-%m-%dT%H:%M:%S")}

    # If no gap is found, return the end time of the last appointment
    return {"first_available": (appointments[-1].appointment_date + appointments[-1].end_time).strftime("%Y-%m-%dT%H:%M:%S")}

