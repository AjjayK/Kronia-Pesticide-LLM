# Kronia

### Your AI Powered Pocket Agronomist for Pesticides

[**_Built for Snowflake Mistral Hackathon_**](https://snowflake-mistral-rag.devpost.com/)

[**_Also check the ingestion pipeline repo_**](https://github.com/AjjayK/sf-epa-data-ingestion)

[Link to the App](https://kronia.streamlit.app/)

Kronia is a LLM-powered chat app for getting information and recommendations about pests and pesticide products. Presently, Kronia can be used to chat with pesticide label documents with added context about weather by using user-entered location. Kronia is also multimodal when you upload an image and ask questions about it.

---

## Why Kronia?

Agriculture is one of the overlooked economies, and pesticide selection is one of the frequently faced problem

Not only do pests influence pesticide selection, but also environmental conditions like temperature and rainfall, crop characteristics such as growth stage and tolerance, and safety considerations including human health risks and environmental impact play crucial roles in choosing the right pesticide.

With the above parameters, there are about **57,588 active pesticides registered with the EPA**, and there are about **8,894 pests listed in the Environmental Protection Agency (EPA) database** [1].

Working in an agricultural company, I found that there are over **400 different commodities grown in the US**, and about **20-40% of crop production globally is lost to pests annually**. The presence of weeds also hurts crop yield. Pests alone cost the global economy around **$300 billion dollars** [2].

It is extremely difficult for a human to solve this problem efficiently at scale, whereas LLMs can.

---

## Interaction Guide

Some of the questions that can be asked to Kronia are:

### General Questions
- Active Ingredient
- Dosage
- Target Crop/Plant
- Target Pest
- PPE Needed
- Environmental Hazards
- Mode of Action

### Specific Questions on Label Documents
- Can I use `<pesticide product>` on my `<crop/plant>`?
- When should I reapply `<pesticide product>`?
- How should I store this pesticide safely?
- What are the first aid instructions in case of exposure?
- Can I mix this pesticide with [another pesticide or fertilizer]?
- What are the buffer zone requirements for this pesticide?

### Weather-Specific Questions
- Is the weather today or tomorrow or in the next few days suitable for application?
- Which day has good weather for pesticide efficacy?
- Based on the weather forecast, give me storage recommendations for `<pesticide product>`.

### Image Context
- Suggest me a pesticide product for the infection in the image.
- Is this crop affected by `<specific disease / pest>`?

---

## Working of the App
![Kronia App Workflow](Kronia%20App%20Workflow.png)
1. Built a front-end chat interface using Streamlit for user interaction.
2. Routed user questions to the Cortex Complete function with the Mistral-Large2 model to:
   - Determine if weather context is needed.
   - Generate parameters for the OpenWeather API to fetch relevant weather data.
3. Made the app multimodal by enabling users to upload images, creating additional context with the GPT-4o model.
4. Utilized Cortex Search to retrieve relevant chunks of information from the database for document-based insights.
5. Assembled multiple contexts—weather, image, chat history, relevant chunks, and user query—into the Cortex Complete function with Mistral-Large2 to generate tailored responses.

---

## References

1. [EPA Pesticides Data Dump](https://www3.epa.gov/pesticides/appril/apprildatadump_public.xlsx)
2. [Researchers Helping Protect Crops from Pests](https://www.nifa.usda.gov/about-nifa/blogs/researchers-helping-protect-crops-pests)
