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
   * **Active Ingredient Information**: Get information about the active ingredients in specific pesticides.
   * **Dosage Requirements**: Learn about proper application rates and concentrations for specific situations.
   * **Target Crop/Plant Compatibility**: Understand which products are safe and effective for your specific crops or plants.
   * **Target Pest Identification**: Get information about which products are effective against specific pests.
   * **PPE Requirements**: Learn about the necessary Personal Protective Equipment for safe application.
   * **Environmental Hazard Assessment**: Understand potential environmental impacts and necessary precautions.
   * **Mode of Action Details**: Learn how specific pesticides work to control pests.

## Specific Questions on Label Documents
   * **Usage Compatibility**: "Can I use [pesticide product] on my [crop/plant]?"
   * **Reapplication Timing**: "When should I reapply [pesticide product]?"
   * **Storage Guidelines**: "How should I store this pesticide safely?"
   * **Safety Protocols**: "What are the first aid instructions in case of exposure?"
   * **Mixture Compatibility**: "Can I mix this pesticide with [another pesticide or fertilizer]?"
   * **Buffer Zone Compliance**: "What are the buffer zone requirements for this pesticide?"

   ## Weather-Specific Questions
   * **Current Application Conditions**: "Is the weather today suitable for application?"
   * **Future Application Planning**: "Which day in the next few days has good weather for pesticide efficacy?"
   * **Storage Recommendations**: "Based on the weather forecast, give me storage recommendations for [pesticide product]."

   ## Image Context Questions
   * **Product Recommendations**: "Suggest me a pesticide product for the infection in the image."
   * **Disease/Pest Identification**: "Is this crop affected by [specific disease/pest]?"

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
