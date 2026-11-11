from django import forms
class ExportForm(forms.Form):
    scope = forms.ChoiceField(label='Kapsam', choices=[('space', 'Bir space'), ('tree', 'Sayfa ve alt sayfaları'), ('all', 'Tüm space’ler')])
    target = forms.CharField(label='Space anahtarı veya sayfa ID', required=False, max_length=200)
    ocr = forms.BooleanField(label='Görsellerden yazıları çıkar (OCR)', required=False)
    vision = forms.BooleanField(label='Görselleri yerel modelle yorumla', required=False)
    def clean(self):
        data = super().clean()
        target = data.get('target', '').strip()
        if data.get('scope') in {'space', 'tree'} and not target:
            self.add_error('target', 'Bir değer girin.')
        if data.get('scope') == 'tree' and (not target.isascii() or not target.isdigit()):
            self.add_error('target', 'Sayfa ID rakamlardan oluşmalı.')
        data['target'] = '' if data.get('scope') == 'all' else target
        return data

class SearchForm(forms.Form):
    query = forms.CharField(label='Ne arıyorsun?', max_length=2000, widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Örneğin: Confluence bağlantısı nasıl kurulur?'}))
    k = forms.IntegerField(label='Vektör aramasından alınacak aday sayısı (K)', min_value=1, max_value=100, initial=20)
    limit = forms.IntegerField(label='Gösterilecek sonuç sayısı', min_value=1, max_value=100, initial=5)
    def clean(self):
        data = super().clean()
        if data.get('k') and data.get('limit') and data['limit'] > data['k']:
            self.add_error('limit', 'Sonuç sayısı K değerini aşamaz.')
        return data
