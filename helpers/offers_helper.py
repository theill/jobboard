from google.appengine.ext import webapp

register = webapp.template.create_template_register()

@register.filter
def format_skills(skills):
  """docstring for format_skills"""
  if len(skills) == 0:
    return "nothing"
  elif len(skills) == 1:
    return skills[0]
  else:
    return ", ".join(skills[:-1]) + ' &amp; ' + skills[-1]
