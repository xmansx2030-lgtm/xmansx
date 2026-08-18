from django.contrib import admin

from academics.models import (
    AcademicYear,
    BellPeriod,
    BellSchedule,
    SchoolWeekDay,
    Semester,
)


class SemesterInline(admin.TabularInline):
    model = Semester
    extra = 0
    readonly_fields = ["created_at", "updated_at"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # منع ربط فصل بمدرسة مغايرة من dropdown
        if db_field.name == "school":
            kwargs["disabled"] = True
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ["name", "school", "start_date", "end_date", "status"]
    list_filter = ["status", "school"]
    search_fields = ["name", "school__name"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [SemesterInline]


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ["name", "academic_year", "school", "sequence", "status"]
    list_filter = ["status", "school"]
    search_fields = ["name", "school__name"]
    readonly_fields = ["created_at", "updated_at"]


class BellPeriodInline(admin.TabularInline):
    model = BellPeriod
    extra = 0
    readonly_fields = ["created_at", "updated_at"]
    exclude = ["school"]  # يورث من الجدول — لا اختيار يدوي


@admin.register(BellSchedule)
class BellScheduleAdmin(admin.ModelAdmin):
    list_display = ["name", "school", "status", "valid_from", "valid_to"]
    list_filter = ["status", "school"]
    search_fields = ["name", "school__name"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [BellPeriodInline]

    def save_formset(self, request, form, formset, change):
        # الحصص المضافة من Admin ترث مدرسة الجدول (منع cross-school FK)
        instances = formset.save(commit=False)
        for obj in instances:
            if isinstance(obj, BellPeriod):
                obj.school = form.instance.school
            obj.save()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()


@admin.register(SchoolWeekDay)
class SchoolWeekDayAdmin(admin.ModelAdmin):
    list_display = ["school", "weekday", "is_school_day", "bell_schedule"]
    list_filter = ["is_school_day", "school"]
    readonly_fields = ["created_at", "updated_at"]
