from django.db import migrations, models


SHORT_NAMES = {
    "CSRS-DEMO": "csrs",
    "DG": "dg",
    "DAF": "daf",
    "DRV": "drv",
    "DRD-DIR": "drd",
    "FIN": "finances",
    "TSI": "tsi",
    "FOR": "formation",
    "VAL": "valorisation",
    "CT": "ct",
    "RSE": "rse",
    "GEI": "gei",
    "ETH": "ethique",
    "SE": "suivi-evaluation",
    "CG": "controle-gestion",
    "RH": "rh",
    "I2A": "intendance",
    "ACH": "achats",
    "DOC": "documentation",
    "DRD": "recherche",
    "CLIN": "clinique",
    "OBS": "observatoires",
    "LAB": "laboratoire",
    "MIC": "microscopie",
    "AX-SAN": "sante",
    "AX-ENV": "environnement",
    "AX-SEC": "securite-alimentaire",
    "AX-SOC": "sciences-sociales",
    "GLP": "glp",
    "PAT": "patrimoine",
    "STA": "stations",
    "UAR": "appui-recherche",
    "UGT": "ressources-techniques",
    "CAP": "capitalisation",
    "AX-BIO": "biodiversite",
    "AX-AGR": "agriculture",
    "MG": "moyens-generaux",
}


def set_compact_short_names(apps, schema_editor):
    """Apply interface labels by stable service code without touching long names."""
    OrganizationUnit = apps.get_model("work", "OrganizationUnit")
    for code, short_name in SHORT_NAMES.items():
        OrganizationUnit.objects.filter(code=code).update(short_name=short_name)


def restore_long_names(apps, schema_editor):
    """Restore the state produced by migration 0010."""
    OrganizationUnit = apps.get_model("work", "OrganizationUnit")
    for code in SHORT_NAMES:
        OrganizationUnit.objects.filter(code=code).update(
            short_name=models.F("long_name")
        )


class Migration(migrations.Migration):
    dependencies = [("work", "0010_normalize_organization_services")]

    operations = [
        migrations.RunPython(set_compact_short_names, restore_long_names),
    ]
