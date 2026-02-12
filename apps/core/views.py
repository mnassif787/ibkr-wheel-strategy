from django.shortcuts import render, redirect


def index(request):
    """Homepage view - redirect to main hub"""
    return redirect('ibkr:hub')
