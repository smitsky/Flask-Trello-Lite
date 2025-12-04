from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Email, EqualTo, Optional

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(1, 100)])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember')
    submit = SubmitField('Log in')

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(1, 100)])
    email = StringField('Email', validators=[Optional(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Repeat Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Create account')