from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    handicap = db.Column(db.Float, nullable=False)
    gross_win = db.Column(db.Boolean, default=False)

class Tournament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)
    score = db.Column(db.Float, nullable=False)
