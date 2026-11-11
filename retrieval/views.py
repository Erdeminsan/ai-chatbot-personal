from functools import wraps
from pathlib import Path
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from .models import ExportJob
from .forms import ExportForm, SearchForm
from .backends import embedder, reranker, RetrievalError
from .index import search_index


def operator(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        # Shared service PAT/index: do not imply document-level ACL support.
        if not request.user.is_staff:
            return HttpResponseForbidden('Bu yerel panel yalnızca yetkili yöneticiler içindir.')
        return view(request, *args, **kwargs)
    return wrapped


@operator
def confluence(request):
    form = ExportForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        ExportJob.objects.create(owner=request.user, **form.cleaned_data)
        return redirect('confluence')
    jobs = ExportJob.objects.filter(owner=request.user)[:30]
    return render(request, 'retrieval/confluence.html', {'form': form, 'jobs': jobs,
                  'refresh': request.method == 'GET' and any(job.status in {'queued', 'running'} for job in jobs)})


@operator
def search(request):
    form = SearchForm(request.POST if request.method == 'POST' else None)
    results, error, searched = [], '', False
    if request.method == 'POST' and form.is_valid():
        try:
            if not Path(settings.RAG_INDEX_PATH).is_file():
                raise RetrievalError('Henüz arama indeksi oluşturulmadı.')
            results = search_index(settings.RAG_INDEX_PATH, form.cleaned_data['query'], embedder(), reranker(),
                                   form.cleaned_data['k'], form.cleaned_data['limit'])
            searched = True
        except RetrievalError as exc:
            error = str(exc)
        except Exception:
            error = 'Arama modeli veya indeks yüklenemedi. Model kurulumunu ve indeks ayarlarını kontrol edin.'
    return render(request, 'retrieval/search.html', {'form': form, 'results': results, 'error': error, 'searched': searched})


@operator
@require_POST
def command(request):
    value = request.POST.get('command', '').strip().lower()
    routes = {'/confluence': 'confluence', '/search': 'search'}
    if value not in routes:
        return render(request, 'retrieval/command.html', {'error': 'Desteklenen komutlar: /confluence ve /search.'}, status=400)
    return redirect(routes[value])
