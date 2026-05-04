from django import forms
from django.utils import timezone
from .models import BudgetCycle, User
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.validators import RegexValidator

class BudgetCycleForm(forms.ModelForm):
    total_allowance = forms.DecimalField(
        min_value=1,
        max_digits=10,
        decimal_places=2,
        help_text='Enter a positive amount'
    )
    
    start_date = forms.DateField(
        initial=timezone.now,
        widget=forms.DateInput(attrs={'type':'date'})
    )
    
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type':'date'})
    )
    
    class Meta:
        model = BudgetCycle
        fields = ['total_allowance', 'start_date', 'end_date']
        
    def clean(self):
        cleaned_data = super().clean() 
        
        start = cleaned_data.get('start_date')
        end = cleaned_data.get('end_date')
        allowance = cleaned_data.get('total_allowance')
        
        if start and end and start >= end:
            raise forms.ValidationError(
                "The end date must be after the start date"
            )
        if allowance < 1:
            raise forms.ValidationError(
                "Allowance must be postive and greater than 0"
            )
            
        return cleaned_data
    
class PinLoginForm(AuthenticationForm):
    username = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs={
            'class':'form-control',
            'placeholder': 'email@example.com'
        })
    )
    
    password = forms.CharField(
        label='4-Digit PIN',
        widget=forms.PasswordInput(attrs={
            'class':'form-control',
            'placeholder': '****',
            'pattern': '[0-9]*',
            'inputmode': 'numeric',
            'maxlength': '4'   
        })
    )

class PinSignupForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        label="Email"
    )
    
    pin_validator = RegexValidator(r'^\d{4}$', 'PIN must be exactly 4 digits.')
    
    password1 = forms.CharField(
        label="4-Digit PIN",
        validators=[pin_validator],
        widget=forms.PasswordInput(attrs={
            'maxlength':'4',
            'inputmode':'numeric'
        })
    )
    
    password2 = forms.CharField(
        label="Confirm PIN",
        validators=[pin_validator],
        widget=forms.PasswordInput(attrs={
            'maxlength':'4',
            'inputmode':'numeric'
        })
    )
    
    class Meta:
        model = User
        fields = ('email', 'username')
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields['password1'].help_text = "Enter a 4-Digit PIN"